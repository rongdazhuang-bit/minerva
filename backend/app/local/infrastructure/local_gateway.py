"""Local filesystem gateway for workspace object file operations."""

from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from app.exceptions import AppError
from app.local.domain.models import LocalDownloadProxy, LocalObjectItem


class LocalGateway:
    """Filesystem-backed gateway rooted at one resolved workspace storage directory."""

    def __init__(self, *, root: Path) -> None:
        """Store the absolute directory root for object key resolution."""

        self._root = root

    def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str | None,
    ) -> None:
        """Write one object body under the gateway root, creating parent directories."""

        _ = content_type
        path = self._object_path(object_key=object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def list_objects(self, *, prefix: str) -> list[LocalObjectItem]:
        """Return object rows under ``prefix``, sorted by mtime descending."""

        search_root = self._root if not prefix else self._root / Path(prefix)
        if not search_root.exists():
            return []

        items: list[LocalObjectItem] = []
        for path in search_root.rglob("*"):
            if not path.is_file():
                continue
            object_key = path.relative_to(self._root).as_posix()
            if prefix and not object_key.startswith(prefix):
                continue
            stat = path.stat()
            items.append(
                LocalObjectItem(
                    object_key=object_key,
                    size=stat.st_size,
                    last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                )
            )
        items.sort(
            key=lambda item: item.last_modified or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return items

    def get_object_bytes(self, *, object_key: str) -> bytes:
        """Read one object body as bytes."""

        path = self._require_object_path(object_key=object_key)
        return path.read_bytes()

    def open_download_stream(self, *, object_key: str) -> LocalDownloadProxy:
        """Open one object for proxy download mode."""

        path = self._require_object_path(object_key=object_key)
        content_type = mimetypes.guess_type(path.name)[0]
        stream = path.open("rb")
        return LocalDownloadProxy(
            stream=stream,
            content_type=content_type,
            content_length=path.stat().st_size,
        )

    def delete_object(self, *, object_key: str) -> None:
        """Delete one object file by key."""

        path = self._require_object_path(object_key=object_key)
        path.unlink()

    def exists(self, *, object_key: str) -> bool:
        """Return True when one object file exists under the gateway root."""

        return self._object_path(object_key=object_key).is_file()

    def _object_path(self, *, object_key: str) -> Path:
        """Map one POSIX object key to an absolute path under the gateway root."""

        return self._root / Path(object_key)

    def _require_object_path(self, *, object_key: str) -> Path:
        """Return object path or raise ``local.object_not_found`` when missing."""

        path = self._object_path(object_key=object_key)
        if not path.is_file():
            raise AppError("local.object_not_found", "Local object not found", 404)
        return path
