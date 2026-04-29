"""HTTP-facing pydantic contracts for Rule Base and Rule Config Prompt APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RuleBaseCreateIn(BaseModel):
    """Validated payload for creating Rule Base rows."""

    sequence_number: int = Field(default=0, ge=-32768, le=32767)
    engineering_code: str | None = Field(default=None, max_length=64)
    subject_code: str | None = Field(default=None, max_length=64)
    serial_number: str | None = Field(default=None, max_length=32)
    document_type: str | None = Field(default=None, max_length=64)
    review_section: str = Field(min_length=1, max_length=128)
    review_object: str = Field(min_length=1, max_length=128)
    review_rules: str = Field(min_length=1, max_length=1_000_000)
    review_rules_ai: str | None = Field(default=None, max_length=1_000_000)
    review_result: str = Field(min_length=1, max_length=1_000_000)
    status: Literal["Y", "N"]


class RuleBasePatchIn(BaseModel):
    """Partial update payload with optional fields mirroring ``RuleBase`` columns."""

    sequence_number: int | None = Field(default=None, ge=-32768, le=32767)
    engineering_code: str | None = Field(default=None, max_length=64)
    subject_code: str | None = Field(default=None, max_length=64)
    serial_number: str | None = Field(default=None, max_length=32)
    document_type: str | None = Field(default=None, max_length=64)
    review_section: str | None = Field(default=None, min_length=1, max_length=128)
    review_object: str | None = Field(default=None, min_length=1, max_length=128)
    review_rules: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    review_rules_ai: str | None = Field(default=None, max_length=1_000_000)
    review_result: str | None = Field(default=None, min_length=1, max_length=1_000_000)
    status: Literal["Y", "N"] | None = None


class RuleBaseListItemOut(BaseModel):
    """Single Rule Base projection returned by list/detail endpoints."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    sequence_number: int
    engineering_code: str | None
    subject_code: str | None
    serial_number: str | None
    document_type: str | None
    review_section: str
    review_object: str
    review_rules: str
    review_rules_ai: str | None
    review_result: str
    status: str
    create_at: datetime | None
    update_at: datetime | None


class RuleBaseListPageOut(BaseModel):
    """Paginated list envelope."""

    items: list[RuleBaseListItemOut]
    total: int


class RuleBasePolishReviewRulesIn(BaseModel):
    """与表单「工程 / 专业 / 文档类型」一致，用于匹配 rule_config_prompt；空或缺省按规范化后为 NULL。"""

    engineering_code: str | None = Field(default=None, max_length=64)
    subject_code: str | None = Field(default=None, max_length=64)
    document_type: str | None = Field(default=None, max_length=64)
    review_rules: str = Field(min_length=1, max_length=1_000_000)


class RuleBasePolishReviewRulesOut(BaseModel):
    """AI-polished review rule text."""

    review_rules_ai: str


class RuleConfigPromptCreateIn(BaseModel):
    """Payload defining prompts tied to model provider rows."""

    model_id: uuid.UUID
    engineering_code: str | None = Field(default=None, max_length=64)
    subject_code: str | None = Field(default=None, max_length=64)
    document_type: str | None = Field(default=None, max_length=64)
    sys_prompt: str | None = Field(default=None, max_length=1024)
    user_prompt: str | None = Field(default=None, max_length=1_000_000)
    chat_memory: str | None = Field(default=None, max_length=1_000_000)


class RuleConfigPromptPatchIn(BaseModel):
    """Partial updates for prompt triplets."""

    model_id: uuid.UUID | None = None
    engineering_code: str | None = Field(default=None, max_length=64)
    subject_code: str | None = Field(default=None, max_length=64)
    document_type: str | None = Field(default=None, max_length=64)
    sys_prompt: str | None = Field(default=None, max_length=1024)
    user_prompt: str | None = Field(default=None, max_length=1_000_000)
    chat_memory: str | None = Field(default=None, max_length=1_000_000)


class RuleConfigPromptListItemOut(BaseModel):
    """Joined prompt row plus resolved provider/model labels."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    model_id: uuid.UUID
    provider_name: str
    model_name: str
    engineering_code: str | None
    subject_code: str | None
    document_type: str | None
    sys_prompt: str | None
    user_prompt: str | None
    chat_memory: str | None
    create_at: datetime | None
    update_at: datetime | None


class RuleConfigPromptListPageOut(BaseModel):
    """Paginated prompt configuration view."""

    items: list[RuleConfigPromptListItemOut]
    total: int


class RuleBaseOverviewStatsOut(BaseModel):
    """Facet counters backing dashboard filters."""

    rule_count: int = Field(ge=0)
    engineering_codes: list[str] = Field(default_factory=list)
    subject_codes: list[str] = Field(default_factory=list)
    document_type_codes: list[str] = Field(default_factory=list)
