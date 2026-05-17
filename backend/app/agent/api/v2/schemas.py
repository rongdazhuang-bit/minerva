"""Pydantic request/response models for agent HTTP API v2."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
    updated_at: datetime | None = None


class AgentSessionListItemOut(BaseModel):
    """Sidebar row for a recent agent session."""

    id: UUID
    title: str | None
    preview: str | None
    created_at: datetime
    updated_at: datetime | None


class AgentSessionListOut(BaseModel):
    """Recent sessions for the workspace agent UI."""

    sessions: list[AgentSessionListItemOut]
    has_more: bool = False
    next_cursor: str | None = None


class AgentMessageOut(BaseModel):
    """One persisted chat message for session restore."""

    id: UUID
    role: str
    content: str | None
    seq: int
    created_at: datetime


class AgentSessionDetailOut(BaseModel):
    """Session metadata plus ordered messages."""

    session: AgentSessionOut
    messages: list[AgentMessageOut]


class AgentSkillItemOut(BaseModel):
    """One built-in agent skill."""

    id: str
    description: str


class AgentSkillListOut(BaseModel):
    """Skills available to the planner."""

    skills: list[AgentSkillItemOut]


class AgentRunCreateV2(BaseModel):
    """发起一次 v2 run（服务端托管模型连接）。"""

    user_message: str = Field(min_length=1)
    model_id: UUID
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    preferred_skills: list[str] = Field(default_factory=list)
