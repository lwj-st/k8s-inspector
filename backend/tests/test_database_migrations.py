from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.migrate import (
    BASELINE_REVISION,
    HEAD_REVISION,
    build_alembic_config,
    current_revision,
    downgrade_database,
    upgrade_database,
)
from app.security.crypto import SensitiveValueCipher


TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _settings(path: Path, *, encryption_key: str | None = TEST_KEY) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{path}",
        encryption_key=encryption_key,
    )


def test_empty_database_initializes_to_v110_head(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "empty.db")

    assert upgrade_database(settings) == HEAD_REVISION
    engine = create_engine(settings.database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "issues",
            "issue_scope_memberships",
            "inspection_runs",
            "admin_sessions",
            "security_audit_logs",
        } <= tables
        for table_name in (
            "issues",
            "issue_scope_memberships",
            "issue_events",
            "inspection_plans",
            "inspection_runs",
            "inspection_check_results",
            "notification_channels",
            "notification_deliveries",
            "resource_metric_states",
            "security_audit_logs",
            "admin_sessions",
        ):
            database_columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
            assert database_columns == set(Base.metadata.tables[table_name].columns.keys())
        constraints = inspect(engine).get_unique_constraints("inspection_check_results")
        assert any(
            constraint["column_names"] == ["run_id", "check_code", "scope_key"]
            for constraint in constraints
        )
        membership_pk = inspect(engine).get_pk_constraint("issue_scope_memberships")
        assert membership_pk["constrained_columns"] == ["issue_id", "scope_key"]
        membership_fks = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspect(engine).get_foreign_keys("issue_scope_memberships")
        }
        assert membership_fks[("issue_id",)]["referred_table"] == "issues"
        assert membership_fks[("issue_id",)]["options"]["ondelete"] == "CASCADE"
        assert membership_fks[("last_seen_run_id",)]["referred_table"] == "inspection_runs"
        assert membership_fks[("last_seen_run_id",)]["options"]["ondelete"] == "SET NULL"
        membership_indexes = inspect(engine).get_indexes("issue_scope_memberships")
        assert [
            (index["name"], index["column_names"])
            for index in membership_indexes
        ] == [
            (
                "ix_issue_scope_memberships_scope_active",
                ["scope_key", "active"],
            )
        ]
        membership_checks = inspect(engine).get_check_constraints("issue_scope_memberships")
        assert [constraint["name"] for constraint in membership_checks] == [
            "ck_issue_scope_memberships_active_deactivated"
        ]
        issue_columns = {column["name"] for column in inspect(engine).get_columns("issues")}
        assert "scope_key" not in issue_columns
        settings_columns = {column["name"] for column in inspect(engine).get_columns("system_settings")}
        assert "cluster_id" in settings_columns
    finally:
        engine.dispose()


def test_issue_scope_membership_supports_multiple_scopes_and_fk_actions(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "membership.db")
    assert upgrade_database(settings) == HEAD_REVISION
    engine = create_engine(settings.database_url)
    now = datetime.now(timezone.utc)
    issues = Base.metadata.tables["issues"]
    runs = Base.metadata.tables["inspection_runs"]
    memberships = Base.metadata.tables["issue_scope_memberships"]

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            issue_id = connection.execute(
                issues.insert().values(
                    cluster_id="default",
                    issue_code="POD_NOT_READY",
                    fingerprint="a" * 64,
                    severity="warning",
                    status="open",
                    scope="pod",
                    resource_kind="Pod",
                    resource_namespace="demo",
                    resource_name="api-0",
                    summary="Pod 未就绪",
                    reason="Ready=False",
                    suggestion="检查探针",
                    first_seen_at=now,
                    last_seen_at=now,
                    source_check="pod.runtime",
                )
            ).inserted_primary_key[0]
            run_id = connection.execute(
                runs.insert().values(
                    trigger="scheduled",
                    status="succeeded",
                    scope={"type": "cluster"},
                )
            ).inserted_primary_key[0]
            connection.execute(
                memberships.insert(),
                [
                    {
                        "issue_id": issue_id,
                        "scope_key": "a" * 64,
                        "last_seen_run_id": run_id,
                        "last_seen_at": now,
                    },
                    {
                        "issue_id": issue_id,
                        "scope_key": "b" * 64,
                        "last_seen_run_id": run_id,
                        "last_seen_at": now,
                    },
                ],
            )

            rows = connection.execute(
                select(
                    memberships.c.scope_key,
                    memberships.c.active,
                    memberships.c.last_seen_run_id,
                ).order_by(memberships.c.scope_key)
            ).all()
            assert rows == [
                ("a" * 64, True, run_id),
                ("b" * 64, True, run_id),
            ]

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        memberships.insert().values(
                            issue_id=issue_id,
                            scope_key="c" * 64,
                            active=True,
                            last_seen_run_id=run_id,
                            last_seen_at=now,
                            deactivated_at=now,
                        )
                    )

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        memberships.insert().values(
                            issue_id=issue_id,
                            scope_key="d" * 64,
                            active=False,
                            last_seen_run_id=run_id,
                            last_seen_at=now,
                        )
                    )

            connection.execute(runs.delete().where(runs.c.id == run_id))
            assert connection.execute(
                select(memberships.c.last_seen_run_id)
            ).scalars().all() == [None, None]

            connection.execute(issues.delete().where(issues.c.id == issue_id))
            assert connection.scalar(
                select(func.count()).select_from(memberships)
            ) == 0
    finally:
        engine.dispose()


def test_v100_plaintext_api_key_upgrades_encrypted_and_downgrades_for_rollback(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "upgrade.db")
    config = build_alembic_config(settings)
    command.upgrade(config, BASELINE_REVISION)
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO system_settings "
                "(id, base_path, provider_mode, llm_enabled, llm_provider, api_key, "
                "default_inspection_strategy) "
                "VALUES (1, '', 'mock', 0, 'qwen', :api_key, '{}')"
            ),
            {"api_key": "legacy-api-key"},
        )

    assert upgrade_database(settings) == HEAD_REVISION
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT api_key, api_key_encrypted FROM system_settings WHERE id = 1")
        ).one()
    assert row.api_key is None
    assert "legacy-api-key" not in row.api_key_encrypted
    assert (
        SensitiveValueCipher.from_key(TEST_KEY).decrypt(
            row.api_key_encrypted,
            purpose="llm_api_key",
        )
        == "legacy-api-key"
    )

    assert downgrade_database(settings) == BASELINE_REVISION
    with engine.connect() as connection:
        restored = connection.execute(
            text("SELECT api_key FROM system_settings WHERE id = 1")
        ).scalar_one()
    assert restored == "legacy-api-key"
    assert "issues" not in inspect(engine).get_table_names()
    assert "issue_scope_memberships" not in inspect(engine).get_table_names()
    engine.dispose()


def test_legacy_secret_without_encryption_key_fails_without_marking_head(
    tmp_path: Path,
) -> None:
    initial = _settings(tmp_path / "failure.db")
    command.upgrade(build_alembic_config(initial), BASELINE_REVISION)
    engine = create_engine(initial.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO system_settings "
                "(id, base_path, provider_mode, llm_enabled, llm_provider, api_key, "
                "default_inspection_strategy) "
                "VALUES (1, '', 'mock', 0, 'qwen', :api_key, '{}')"
            ),
            {"api_key": "must-not-leak"},
        )

    missing_key = _settings(tmp_path / "failure.db", encryption_key=None)
    with pytest.raises(Exception, match="加密密钥"):
        upgrade_database(missing_key)
    assert current_revision(missing_key) == BASELINE_REVISION

    assert upgrade_database(initial) == HEAD_REVISION
    engine.dispose()
