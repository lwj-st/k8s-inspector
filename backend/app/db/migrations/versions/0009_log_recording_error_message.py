"""Add log recording failure detail."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "log_recording_error_message"
down_revision: str | Sequence[str] | None = "log_recording_namespaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("log_recordings", sa.Column("error_message", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("log_recordings", "error_message")
