"""SQLAlchemy model for global navigation menus."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysMenu(Base):
    """Global sidebar/menu row; parent_id references another sys_menu.id (app-enforced)."""

    __tablename__ = "sys_menu"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    menu_name: Mapped[str] = mapped_column(String(64), nullable=False)
    i18n_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    menu_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_num: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    menu_type: Mapped[str] = mapped_column(String(1), nullable=False)
    perms: Mapped[str | None] = mapped_column(String(128), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false())
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
