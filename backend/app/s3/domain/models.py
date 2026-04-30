"""Domain models shared by S3 API, service, and infrastructure layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO


@dataclass(frozen=True)
class S3StorageConfig:
    """Validated workspace S3 storage configuration loaded from ``sys_storage``."""

    bucket: str
    endpoint_url: str | None
    auth_type: str
    api_key: str | None
    auth_name: str | None
    auth_passwd: str | None


@dataclass(frozen=True)
class S3ObjectItem:
    """One object row projected from S3 list APIs."""

    object_key: str
    size: int
    last_modified: datetime | None


@dataclass(frozen=True)
class S3ListPage:
    """Paginated list result returned by service layer."""

    items: list[S3ObjectItem]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class S3UploadResult:
    """Upload result containing persisted object metadata."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str


@dataclass(frozen=True)
class S3DownloadRedirect:
    """Download response data for redirect mode."""

    url: str


@dataclass(frozen=True)
class S3DownloadProxy:
    """Download response data for proxy streaming mode."""

    stream: BinaryIO
    content_type: str | None
    content_length: int | None
