from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.config import Settings, get_settings
from app.db.session import build_engine


BASELINE_REVISION = "v100_baseline"
HEAD_REVISION = "maintenance_silence_windows"
MIGRATION_DIR = Path(__file__).resolve().parent / "migrations"
V100_TABLES = {
    "diagnosis_records",
    "fault_templates",
    "inspection_records",
    "keyword_rules",
    "saved_inspection_targets",
    "system_settings",
    "whitelists",
}


class MigrationStateError(RuntimeError):
    pass


def build_alembic_config(settings: Settings) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATION_DIR))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    config.attributes["encryption_key"] = settings.encryption_key
    return config


def upgrade_database(settings: Settings) -> str:
    config = build_alembic_config(settings)
    engine = build_engine(settings)
    try:
        existing = set(inspect(engine).get_table_names())
        if "alembic_version" not in existing and existing:
            missing = V100_TABLES - existing
            if missing:
                names = ", ".join(sorted(missing))
                raise MigrationStateError(f"数据库不是可识别的 v1.0.0 schema，缺少表：{names}")
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")
        return current_revision(settings)
    finally:
        engine.dispose()


def downgrade_database(settings: Settings, revision: str = BASELINE_REVISION) -> str:
    config = build_alembic_config(settings)
    command.downgrade(config, revision)
    return current_revision(settings)


def current_revision(settings: Settings) -> str:
    engine = build_engine(settings)
    try:
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" not in tables:
            return "unversioned"
        with engine.connect() as connection:
            value = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one_or_none()
            return value or "unversioned"
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="K8s Inspector database migration")
    parser.add_argument("action", choices=("upgrade", "downgrade", "current"))
    parser.add_argument("--revision", default=BASELINE_REVISION)
    args = parser.parse_args()
    settings = get_settings()
    if args.action == "upgrade":
        print(upgrade_database(settings))
    elif args.action == "downgrade":
        print(downgrade_database(settings, args.revision))
    else:
        print(current_revision(settings))


if __name__ == "__main__":
    main()
