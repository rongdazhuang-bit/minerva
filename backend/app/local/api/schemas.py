"""Pydantic models for workspace local file API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LocalDownloadMode(str, Enum):
    """Supported file download modes."""

    redirect = "redirect"
    proxy = "proxy"


class LocalFileUploadOut(BaseModel):
    """Upload API response payload."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str


class LocalFileListItemOut(BaseModel):
    """One list row projected from local filesystem objects."""

    object_key: str
    size: int
    last_modified: datetime | None


class LocalFileListOut(BaseModel):
    """Paginated list response for workspace local files."""

    items: list[LocalFileListItemOut]
    total: int
    page: int
    page_size: int = Field(ge=1)
