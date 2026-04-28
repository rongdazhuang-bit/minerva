from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RuleBaseCreateIn(BaseModel):
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
    items: list[RuleBaseListItemOut]
    total: int


class RuleBasePolishReviewRulesIn(BaseModel):
    review_rules: str = Field(min_length=1, max_length=1_000_000)


class RuleBasePolishReviewRulesOut(BaseModel):
    review_rules_ai: str
