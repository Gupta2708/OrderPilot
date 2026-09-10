"""Persist live run progress: last wake, run statistics, and ordered activities."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("last_wake_at", sa.DateTime(timezone=True)))
    op.add_column(
        "runs",
        sa.Column(
            "stats", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    # The workflow assigns a monotonic sequence per run. Making it unique lets
    # the persistence Activity retry safely without duplicating timeline rows.
    op.add_column("activities", sa.Column("seq", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_activities_run_id_seq", "activities", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_constraint("uq_activities_run_id_seq", "activities", type_="unique")
    op.drop_column("activities", "seq")
    op.drop_column("runs", "stats")
    op.drop_column("runs", "last_wake_at")
