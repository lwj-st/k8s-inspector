from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import (
    InspectionCheckResult,
    Issue,
    IssueScopeMembership,
    NotificationChannel,
    NotificationDelivery,
)


def test_inspection_check_result_uses_frozen_three_column_uniqueness() -> None:
    unique_sets = {
        tuple(constraint.columns.keys())
        for constraint in InspectionCheckResult.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert unique_sets == {("run_id", "check_code", "scope_key")}


def test_notification_delivery_keeps_required_channel_reference_for_soft_delete() -> None:
    channel_id = NotificationDelivery.__table__.c.channel_id
    assert channel_id.nullable is False
    assert next(iter(channel_id.foreign_keys)).ondelete == "RESTRICT"
    assert "channel_name" not in NotificationDelivery.__table__.c
    assert "deleted_at" in NotificationChannel.__table__.c


def test_issue_scope_membership_uses_composite_identity_and_required_lifecycle_fields() -> None:
    table = IssueScopeMembership.__table__

    assert tuple(table.primary_key.columns.keys()) == ("issue_id", "scope_key")
    assert table.c.scope_key.type.length == 64
    assert table.c.active.nullable is False
    assert table.c.active.default.arg is True
    assert table.c.active.server_default is not None
    assert table.c.last_seen_run_id.nullable is True
    assert table.c.last_seen_at.nullable is False
    assert table.c.deactivated_at.nullable is True
    assert table.c.issue_id.unique is not True
    assert "scope_key" not in Issue.__table__.c

    foreign_keys = {
        column_name: next(iter(table.c[column_name].foreign_keys))
        for column_name in ("issue_id", "last_seen_run_id")
    }
    assert foreign_keys["issue_id"].target_fullname == "issues.id"
    assert foreign_keys["issue_id"].ondelete == "CASCADE"
    assert foreign_keys["last_seen_run_id"].target_fullname == "inspection_runs.id"
    assert foreign_keys["last_seen_run_id"].ondelete == "SET NULL"

    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert indexes == {
        "ix_issue_scope_memberships_scope_active": ("scope_key", "active"),
    }

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert checks == {
        "ck_issue_scope_memberships_active_deactivated": (
            "(active AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_at IS NOT NULL)"
        ),
    }
