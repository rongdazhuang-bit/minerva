"""ORM for workspace-scoped MCP client and server configuration rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysMcpClient(Base):
    """External MCP server connection config for one workspace (Minerva acts as MCP client)."""

    __tablename__ = "sys_mcp_client"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    secrets: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_test_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SysMcpServer(Base):
    """Outbound MCP server exposure config for one workspace."""

    __tablename__ = "sys_mcp_server"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    exposure: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    auth_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="NONE"
    )
    auth_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
