"""Add namespace to log recording template matches."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "log_recording_match_namespace"
down_revision: str | Sequence[str] | None = "log_recording_pod_container_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("log_recording_template_matches", sa.Column("namespace", sa.String(253), nullable=True))


def downgrade() -> None:
    op.drop_column("log_recording_template_matches", "namespace")
