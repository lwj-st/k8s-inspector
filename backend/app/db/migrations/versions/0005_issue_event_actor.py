"""Add actor to issue events for manual handling records."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "issue_event_actor"
down_revision: str | Sequence[str] | None = "admin_password_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("issue_events")}
    if "actor" not in existing_columns:
        op.add_column("issue_events", sa.Column("actor", sa.String(128), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("issue_events")}
    if "actor" in existing_columns:
        with op.batch_alter_table("issue_events") as batch:
            batch.drop_column("actor")
