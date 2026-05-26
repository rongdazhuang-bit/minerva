"""Pydantic request/response models for agent HTTP API v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
    usage: dict[str, Any] | None = Field(
        default=None,
        description="累计 token 用量(JSON，同 usage_json)",
    )


class AgentSessionListItemOut(BaseModel):
    """Sidebar row for a recent agent session."""

    id: UUID
    title: str | None
    preview: str | None
    created_at: datetime
    updated_at: datetime | None
    usage: dict[str, Any] | None = None


class AgentSessionListOut(BaseModel):
    """Recent sessions for the workspace agent UI."""

    sessions: list[AgentSessionListItemOut]
    has_more: bool = False
    next_cursor: str | None = None


class AgentMessageReasoningSegmentOut(BaseModel):
    """One visible reasoning phase within an assistant message."""

    phase: str
    step_id: str | None = None
    skill_id: str | None = None
    text: str
    reasoning_tokens: int = Field(ge=0)


class AgentMessageReasoningOut(BaseModel):
    """Structured reasoning payload stored on assistant ``meta_json.reasoning``."""

    segments: list[AgentMessageReasoningSegmentOut]
    reasoning_tokens: int = Field(ge=0)


class AgentMessageOut(BaseModel):
    """One persisted chat message for session restore."""

    id: UUID
    role: str
    content: str | None
    seq: int
    created_at: datetime
    meta_json: dict[str, Any] | None = None
    reasoning_text: str | None = None
    reasoning: AgentMessageReasoningOut | None = None


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


class AgentOverviewUsageDailyStatItemOut(BaseModel):
    """One calendar day bucket for the workspace agent token usage chart."""

    date: str = Field(min_length=10, max_length=10)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)


class AgentOverviewUsageDailyStatsOut(BaseModel):
    """Fixed window of daily agent token usage (see service ``DAY_COUNT``)."""

    items: list[AgentOverviewUsageDailyStatItemOut] = Field(min_length=7, max_length=7)


class AgentRunCreateV2(BaseModel):
    """发起一次 v2 run（服务端托管模型连接）。"""

    user_message: str = Field(min_length=1)
    model_id: UUID
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    preferred_skills: list[str] = Field(default_factory=list)
    regenerate_from_message_id: UUID | None = Field(
        default=None,
        description="重新生成：从该助手消息起截断会话历史（含该条），不再重复写入用户消息。",
    )
    regenerate_last_assistant: bool = Field(
        default=False,
        description="重新生成：截断最后一条助手消息及其后的记录（无需 message id）。",
    )
    enable_thinking: bool | None = Field(
        default=None,
        description="是否开启思考模式；null 表示按 model_config / 全局默认。",
    )
