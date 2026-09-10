"""Initial product tables; no order lifecycle implementation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supervisors",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_instruction", sa.Text(), nullable=False),
        sa.Column("allowed_actions", postgresql.JSONB(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("order_id", sa.String(200), nullable=False, unique=True),
        sa.Column("supervisor_id", sa.UUID(), sa.ForeignKey("supervisors.id"), nullable=False),
        sa.Column("temporal_workflow_id", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("order_state", postgresql.JSONB(), nullable=False),
        sa.Column("memory_summary", sa.Text(), nullable=False),
        sa.Column("run_instructions", postgresql.JSONB(), nullable=False),
        sa.Column("next_wake_at", sa.DateTime(timezone=True)),
        sa.Column("latest_decision", postgresql.JSONB()),
        sa.Column("final_output", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_table(
        "activities",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_activities_run_id_created_at", "activities", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_table("activities")
    op.drop_table("runs")
    op.drop_table("supervisors")
