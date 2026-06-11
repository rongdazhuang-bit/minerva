"""SQLAlchemy models for workspace-scoped roles and role-menu links."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysRole(Base):
    """RBAC role row scoped to one workspace."""

    __tablename__ = "sys_role"
    __table_args__ = (
        UniqueConstraint("workspace_id", "role_key", name="uq_sys_role_workspace_role_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
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


class SysRoleMenu(Base):
    """Maps a workspace role to a global sys_menu id (app-enforced)."""

    __tablename__ = "sys_role_menu"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_id", name="uq_sys_role_menu_role_menu"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
