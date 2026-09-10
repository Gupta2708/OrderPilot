import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Supervisor(Base):
    __tablename__ = "supervisors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    base_instruction: Mapped[str] = mapped_column(Text)
    allowed_actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[str] = mapped_column(String(200), unique=True)
    supervisor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("supervisors.id"))
    temporal_workflow_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    order_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    run_instructions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    next_wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    final_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityRecord(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_run_id_created_at", "run_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    type: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
