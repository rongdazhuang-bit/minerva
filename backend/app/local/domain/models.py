"""Domain models shared by local API, service, and infrastructure layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO


@dataclass(frozen=True)
class LocalObjectItem:
    """One object row projected from local filesystem listing."""

    object_key: str
    size: int
    last_modified: datetime | None


@dataclass(frozen=True)
class LocalListPage:
    """Paginated list result returned by service layer."""

    items: list[LocalObjectItem]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class LocalUploadResult:
    """Upload result containing persisted object metadata."""

    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str


@dataclass(frozen=True)
class LocalDownloadRedirect:
    """Download response data for redirect mode."""

    url: str


@dataclass(frozen=True)
class LocalDownloadProxy:
    """Download response data for proxy streaming mode."""

    stream: BinaryIO
    content_type: str | None
    content_length: int | None
