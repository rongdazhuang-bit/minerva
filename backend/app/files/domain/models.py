"""Workspace-scoped file upload domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceFileUploadResult:
    """Unified upload result for S3 or local active storage."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str
