from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysModel(Base):
    __tablename__ = "sys_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    load_balancing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )
    auth_type: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auth_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auth_passwd: Mapped[str | None] = mapped_column(String(128), nullable=True)
    context_size: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    max_tokens_to_sample: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    model_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
