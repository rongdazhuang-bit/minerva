"""Pydantic request/response models for agent HTTP APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.llm.domain.models import ProviderKind


class AgentSessionCreateIn(BaseModel):
    """创建会话时的可选展示字段。"""

    title: str | None = Field(default=None, max_length=200)
    agent_key: str | None = Field(default=None, max_length=64)


class AgentSessionOut(BaseModel):
    """返回给前端的会话标识与时间戳。"""

    id: UUID
    workspace_id: UUID
    title: str | None
    agent_key: str | None
    status: str
    created_at: datetime


class AgentRunCreateIn(BaseModel):
    """发起一次 run：用户消息与上游模型连接参数。"""

    user_message: str = Field(min_length=1)
    skill_ids: list[str] = Field(default_factory=list)
    provider_kind: ProviderKind = ProviderKind.openai_compatible
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
