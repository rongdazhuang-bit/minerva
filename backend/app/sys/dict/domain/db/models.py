from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysDict(Base):
    __tablename__ = "sys_dict"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dict_code",
            name="uq_sys_dict_workspace_dict_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dict_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dict_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dict_sort: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=0)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SysDictItem(Base):
    __tablename__ = "sys_dict_item"
    __table_args__ = (
        UniqueConstraint("dict_uuid", "code", name="uq_sys_dict_item_dict_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dict_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_dict.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    parent_uuid: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sys_dict_item.id", ondelete="RESTRICT"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    item_sort: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=0)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
