"""Identity ORM models: accounts, tenants, workspaces, memberships, refresh tokens."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class MembershipRole(str, enum.Enum):
    """Tenant/workspace authorization role bucket."""

    admin = "admin"
    member = "member"


class User(Base):
    """Authenticated principal with unique email, profile fields, and bcrypt hash."""

    __tablename__ = "sys_user"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    department_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Tenant(Base):
    """Top-level org boundary identified by stable slug."""

    __tablename__ = "sys_tenant"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Workspace(Base):
    """Collaboration scope under one tenant (slug unique per tenant)."""

    __tablename__ = "sys_workspaces"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_sys_workspaces_tenant_slug"),
    )


class TenantMembership(Base):
    """Join row tying a user to a tenant with ``MembershipRole``."""

    __tablename__ = "sys_tenant_user"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="tenant_role"), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_sys_tenant_user"),
    )


class WorkspaceMembership(Base):
    """Join row tying a user to a workspace with ``MembershipRole``."""

    __tablename__ = "sys_workspace_user"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="workspace_role"), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_sys_workspace_user"),
    )


class RefreshToken(Base):
    """Opaque refresh session keyed by ``jti`` with revocation metadata."""

    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    jti: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
