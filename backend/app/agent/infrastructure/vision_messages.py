"""Build LangChain multimodal user messages from stored image attachments."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage

from app.files.service.workspace_file_service import WorkspaceFileService


@dataclass
class VisionAttachmentCache:
    """Run-scoped cache mapping object_key to base64 data URLs."""

    _data_urls: dict[str, str] = field(default_factory=dict)

    def get(self, object_key: str) -> str | None:
        """Return cached data URL for one object key."""

        return self._data_urls.get(object_key)

    def put(self, object_key: str, data_url: str) -> None:
        """Store one data URL for reuse within the same run."""

        self._data_urls[object_key] = data_url


async def build_vision_human_message(
    text: str,
    attachments: list[dict],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_images: bool = True,
) -> HumanMessage:
    """Build a user message with optional vision image parts from stored attachments."""

    body = (text or "").strip()
    if not attachments or not include_images:
        return HumanMessage(content=body)

    parts: list[dict] = []
    if body:
        parts.append({"type": "text", "text": body})

    for attachment in attachments:
        object_key = str(attachment.get("object_key") or "").strip()
        if not object_key:
            continue
        data_url = cache.get(object_key)
        if data_url is None:
            raw = await file_service.read_object_bytes(
                workspace_id=workspace_id,
                object_key=object_key,
            )
            content_type = str(attachment.get("content_type") or "application/octet-stream")
            if content_type == "image/jpg":
                content_type = "image/jpeg"
            encoded = base64.b64encode(raw).decode("ascii")
            data_url = f"data:{content_type};base64,{encoded}"
            cache.put(object_key, data_url)
        parts.append({"type": "image_url", "image_url": {"url": data_url}})

    if not parts:
        return HumanMessage(content=body)
    if len(parts) == 1 and parts[0].get("type") == "text":
        return HumanMessage(content=body)
    return HumanMessage(content=parts)
