"""Outline JSON validation for PPT maker."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class OutlineMeta(BaseModel):
    """Optional cover metadata."""

    title: str = ""
    subtitle: str = ""


class OutlineDocument(BaseModel):
    """Full presentation outline."""

    meta: OutlineMeta | None = None
    slides: list[dict[str, Any]] = Field(min_length=1)

    @field_validator("slides")
    @classmethod
    def slides_non_empty(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure at least one slide entry exists."""

        if not value:
            raise ValueError("slides must not be empty")
        return value


def validate_outline_dict(data: dict[str, Any]) -> OutlineDocument:
    """Validate and return a parsed outline document."""

    return OutlineDocument.model_validate(data)
