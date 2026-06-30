"""Pydantic request/response models for agent HTTP API v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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
    attachments: list["AgentMessageAttachmentOut"] = Field(default_factory=list)


class AgentMessageAttachmentOut(BaseModel):
    """One attachment referenced by a user message."""

    id: UUID | None = None
    object_key: str
    file_name: str | None = None
    content_type: str | None = None
    size: int | None = None
    kind: str = "file"
    download_url: str | None = None


class AgentSessionDetailOut(BaseModel):
    """Session metadata plus ordered messages."""

    session: AgentSessionOut
    messages: list[AgentMessageOut]


class AgentSkillItemOut(BaseModel):
    """One built-in agent skill."""

    id: str
    description: str
    composer_description: str
    composer_visible: bool = True


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

    user_message: str = ""
    attachments: list["AgentAttachmentIn"] = Field(default_factory=list)
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

    @model_validator(mode="after")
    def _require_message_or_single_preferred_skill(self) -> "AgentRunCreateV2":
        """Allow empty ``user_message`` when skill-only or attachments are present."""

        from app.agent.infrastructure.skill_loader import get_indexed_skill

        if self.user_message.strip() or self.attachments:
            return self
        if len(self.preferred_skills) == 1 and get_indexed_skill(self.preferred_skills[0]):
            return self
        raise ValueError(
            "user_message must not be empty unless preferred_skills contains exactly one valid skill id"
        )


class AgentAttachmentIn(BaseModel):
    """Reference one uploaded vision image for an agent run."""

    object_key: str = Field(min_length=1)
    file_name: str | None = None
    content_type: str | None = None


class AgentAttachmentUploadOut(BaseModel):
    """Upload response for one agent vision image."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str


class AgentConversationModelOut(BaseModel):
    """Agent 对话页可选模型（已由服务端过滤）。"""

    id: UUID
    provider_name: str
    model_name: str
    endpoint_url: str
    max_tokens: int | None = None
    tags: list[str]
    supports_vision: bool = False


class SkillRegistryItemOut(BaseModel):
    """One skill package row in the global skills registry."""

    id: str
    description: str
    file_count: int


class SkillRegistryOut(BaseModel):
    """Indexed skills with on-disk file counts for the management UI."""

    skills: list[SkillRegistryItemOut]


class SkillFileTreeNodeOut(BaseModel):
    """One node in a skill directory file tree."""

    name: str
    path: str
    is_dir: bool
    size: int | None = None
    children: list["SkillFileTreeNodeOut"] = Field(default_factory=list)


class SkillFileContentOut(BaseModel):
    """UTF-8 text payload for one skill file."""

    path: str
    content: str


class SkillFileWriteIn(BaseModel):
    """Request body for saving an editable skill text file."""

    content: str


class SkillWriteResultOut(BaseModel):
    """Result of a write that may have refreshed skill_loader caches."""

    path: str
    cache_reloaded: bool = True


class AgentV2ConfigOut(BaseModel):
    """Runtime agent feature flags exposed to the frontend."""

    memory_backend: str
    vision_image_max_count: int = 1
    vision_image_max_bytes: int = 5_242_880
    vision_image_allowed_mime: list[str] = Field(default_factory=list)
    attachment_max_count: int = 5
    attachment_max_bytes: int = 5_242_880
    attachment_allowed_mime: list[str] = Field(default_factory=list)


class AgentMemoryProfileOut(BaseModel):
    """Persistent workspace or session memory profile."""

    id: UUID
    workspace_id: UUID
    session_id: UUID | None
    profile_text: str
    updated_by: UUID | None
    updated_at: datetime


class AgentMemoryProfileCreateIn(BaseModel):
    """Create or replace profile text for a scope."""

    session_id: UUID | None = None
    profile_text: str = Field(min_length=0, max_length=8000)


class AgentMemoryProfilePatchIn(BaseModel):
    """Update profile body."""

    profile_text: str = Field(min_length=0, max_length=8000)


class AgentMem0MemoryItemOut(BaseModel):
    """One mem0 memory row for management UI."""

    id: str
    memory: str
    created_at: str | None = None


class AgentMem0MemoryListOut(BaseModel):
    """Paginated mem0 memories."""

    items: list[AgentMem0MemoryItemOut]
    total: int


SkillFileTreeNodeOut.model_rebuild()
AgentMessageOut.model_rebuild()
AgentRunCreateV2.model_rebuild()
