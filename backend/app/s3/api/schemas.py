"""Pydantic models for workspace S3 file API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class S3DownloadMode(str, Enum):
    """Supported file download modes."""

    redirect = "redirect"
    proxy = "proxy"


class S3FileUploadOut(BaseModel):
    """Upload API response payload."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str


class S3FileListItemOut(BaseModel):
    """One list row projected from S3 objects."""

    object_key: str
    size: int
    last_modified: datetime | None


class S3FileListOut(BaseModel):
    """Paginated list response for workspace S3 files."""

    items: list[S3FileListItemOut]
    total: int
    page: int
    page_size: int = Field(ge=1)
