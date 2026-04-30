"""SQLAlchemy model for workspace-scoped celery schedules."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysCelery(Base):
    """Persistent scheduler job definition with execution state fields."""

    __tablename__ = "sys_celery"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "task_code",
            name="uq_sys_celery_workspace_task_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_code: Mapped[str] = mapped_column(String(128), nullable=False)
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task: Mapped[str | None] = mapped_column(String(128), nullable=True)
    args_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    kwargs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("1"))
    status: Mapped[str | None] = mapped_column(String(2), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(128), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
