from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysOcrTool(Base):
    __tablename__ = "sys_ocr_tool"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_passwd: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(128), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
