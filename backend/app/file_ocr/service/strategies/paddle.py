"""PaddleOCR-VL strategy: S3 source fetch, layout-parsing HTTP call, ``ocr_file_paddleocr`` rows."""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.ocr_http_headers import build_ocr_tool_http_headers
from app.file_ocr.service.paddle_ocr_request import build_layout_parsing_request_for_tool
from app.file_ocr.service.s3_object_bytes import read_workspace_object_bytes
from app.ocr.paddleocr.client import post_layout_parsing
from app.sys.tool.ocr.domain.db.models import SysOcrTool

from .base import FileOcrEngineStrategy

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC ``datetime`` for ORM timestamps."""

    return datetime.now(UTC)


class PaddleOcrFileStrategy(FileOcrEngineStrategy):
    """Calls PaddleOCR-VL layout-parsing and stores markdown fragments per page."""

    ocr_type: ClassVar[str] = "PADDLE_OCR"

    async def process(
        self,
        *,
        session: AsyncSession,
        ocr_file: OcrFile,
        tool: SysOcrTool,
    ) -> None:
        """Download the source object, invoke layout-parsing, then persist per-page markdown."""

        url = (tool.url or "").strip()
        if not url:
            raise ValueError("empty Paddle tool url")
        raw = await read_workspace_object_bytes(
            session,
            workspace_id=ocr_file.workspace_id,
            object_key=ocr_file.object_key,
        )
        file_b64 = base64.standard_b64encode(raw).decode("ascii")
        body = build_layout_parsing_request_for_tool(
            file_b64=file_b64,
            file_name=ocr_file.file_name,
            object_key=ocr_file.object_key,
            tool=tool,
        )
        headers = build_ocr_tool_http_headers(tool)
        envelope = await post_layout_parsing(url, body, headers=headers or None)
        result = envelope.result
        pages = list(result.layout_parsing_results) if result and result.layout_parsing_results else []

        await session.execute(
            delete(OcrFilePaddleocr).where(
                OcrFilePaddleocr.workspace_id == ocr_file.workspace_id,
                OcrFilePaddleocr.file_id == ocr_file.id,
            )
        )
        now = _utc_now()
        for idx, page in enumerate(pages):
            md = page.markdown
            text = md.text if md else None
            images = md.images if md else {}
            images_json = json.dumps(images, ensure_ascii=False) if images else None
            session.add(
                OcrFilePaddleocr(
                    id=uuid.uuid4(),
                    workspace_id=ocr_file.workspace_id,
                    file_id=ocr_file.id,
                    page_index=idx,
                    markdown_text=text,
                    markdown_images=images_json,
                    create_at=now,
                    update_at=now,
                )
            )
        ocr_file.page_count = len(pages)
        ocr_file.status = "SUCCESS"
        ocr_file.remark = None
        ocr_file.update_at = now
        _LOGGER.info(
            "paddle ocr success file_id=%s pages=%s log_id=%s",
            ocr_file.id,
            len(pages),
            envelope.log_id,
        )
