from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class RuleBase(Base):
    __tablename__ = "rule_base"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    engineering_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_section: Mapped[str] = mapped_column(String(128), nullable=False)
    review_object: Mapped[str] = mapped_column(String(128), nullable=False)
    review_rules: Mapped[str] = mapped_column(Text, nullable=False)
    review_rules_ai: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_result: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuleConfigPrompt(Base):
    __tablename__ = "rule_config_prompt"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    engineering_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sys_prompt: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
