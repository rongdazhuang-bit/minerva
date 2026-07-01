"""ORM models for RBAC catalog and ABAC grants."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class GrantType(str, enum.Enum):
    """Kind of row stored in ``sys_user_grant``."""

    role = "role"
    direct_permission = "direct_permission"
    tenant_admin = "tenant_admin"


class GrantScopeType(str, enum.Enum):
    """ABAC scope for a user grant."""

    platform = "platform"
    tenant = "tenant"
    workspace = "workspace"


class SysPermission(Base):
    """Platform-wide permission catalog entry."""

    __tablename__ = "sys_permission"
    __table_args__ = (
        UniqueConstraint("perm_code", name="uq_sys_permission_perm_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    perm_code: Mapped[str] = mapped_column(String(128), nullable=False)
    perm_name: Mapped[str] = mapped_column(String(128), nullable=False)
    perm_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_pattern: Mapped[str | None] = mapped_column(String(256), nullable=True)
    menu_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
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


class SysRolePermission(Base):
    """Maps a workspace role to permission catalog rows."""

    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_sys_role_permission_role_perm"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )


class SysTenantPermission(Base):
    """Menu nodes enabled for one tenant by platform super admin."""

    __tablename__ = "sys_tenant_permission"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "menu_id",
            name="uq_sys_tenant_permission_tenant_menu",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    create_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SysUserGrant(Base):
    """Scoped authorization grant for one user."""

    __tablename__ = "sys_user_grant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    grant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    permission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
