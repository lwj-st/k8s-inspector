"""Add multi-namespace log recording tasks."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "log_recording_namespaces"
down_revision: str | Sequence[str] | None = "log_recordings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("log_recordings", sa.Column("namespaces", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("log_recordings", "namespaces")
