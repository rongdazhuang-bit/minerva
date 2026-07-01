"""SQLAlchemy models for tenant-scoped roles and role-permission links."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysRole(Base):
    """RBAC role row scoped to one tenant (optionally one workspace)."""

    __tablename__ = "sys_role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "role_key", name="uq_sys_role_tenant_role_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role_key: Mapped[str] = mapped_column(String(64), nullable=False)
    role_sort: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
