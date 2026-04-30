"""SQLAlchemy mappings for workspace-scoped file storage rows."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysStorage(Base):
    """File storage endpoint and auth settings bound to one workspace."""

    __tablename__ = "sys_storage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    auth_type: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auth_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auth_passwd: Mapped[str | None] = mapped_column(String(128), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
