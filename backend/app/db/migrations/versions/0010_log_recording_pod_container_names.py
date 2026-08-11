"""Persist log recording pod container names."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "log_recording_pod_container_names"
down_revision: str | Sequence[str] | None = "log_recording_error_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("log_recording_pods", sa.Column("container_names", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("log_recording_pods", "container_names")
