"""PaddleOCR-VL strategy: S3 source fetch, layout-parsing HTTP call, ``ocr_file_paddleocr`` rows."""

from __future__ import annotations

from app.core.log import get_logger
import base64
import json
import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.ocr_http_headers import build_ocr_tool_http_headers
from app.file_ocr.service.paddle_markdown_images import inline_http_markdown_images_to_data_uris
from app.file_ocr.service.paddle_ocr_request import build_layout_parsing_request_for_tool
from app.config import settings
from app.file_ocr.service.s3_object_bytes import read_workspace_object_bytes
from app.layout.from_paddle import layout_page_from_pruned
from app.layout.page_raster import rasterize_source_file, upload_page_rasters
from app.layout.serialize import layout_page_to_blocks_json
from app.layout.to_markdown import page_markdown
from app.ocr.paddleocr.client import post_layout_parsing
from app.sys.tool.ocr.domain.db.models import SysOcrTool

from .base import FileOcrEngineStrategy

log = get_logger(__name__)


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
        page_total = result.effective_page_count() if result else len(pages)

        page_pngs = rasterize_source_file(raw, file_name=ocr_file.file_name)
        raster_keys = await upload_page_rasters(
            session,
            workspace_id=ocr_file.workspace_id,
            ocr_file_id=ocr_file.id,
            page_pngs=page_pngs,
        )

        await session.execute(
            delete(OcrFilePaddleocr).where(
                OcrFilePaddleocr.workspace_id == ocr_file.workspace_id,
                OcrFilePaddleocr.file_id == ocr_file.id,
            )
        )
        now = _utc_now()
        for idx, page in enumerate(pages):
            md = page.markdown
            images = md.images if md else {}
            if images:
                images = await inline_http_markdown_images_to_data_uris(images)
            images_json = json.dumps(images, ensure_ascii=False) if images else None

            layout_blocks_json = None
            page_width = None
            page_height = None
            markdown_text = md.text if md else None
            if page.pruned_result is not None:
                layout_page = layout_page_from_pruned(idx, page.pruned_result)
                layout_blocks_json = layout_page_to_blocks_json(layout_page)
                page_width = layout_page.width
                page_height = layout_page.height
                markdown_text = page_markdown(layout_page, use_translation=False) or markdown_text

            session.add(
                OcrFilePaddleocr(
                    id=uuid.uuid4(),
                    workspace_id=ocr_file.workspace_id,
                    file_id=ocr_file.id,
                    page_index=idx,
                    markdown_text=markdown_text,
                    markdown_images=images_json,
                    page_width=page_width,
                    page_height=page_height,
                    layout_blocks_json=layout_blocks_json,
                    page_raster_object_key=raster_keys.get(idx),
                    layout_version=settings.layout_schema_version,
                    create_at=now,
                    update_at=now,
                )
            )
        ocr_file.page_count = page_total
        ocr_file.status = "SUCCESS"
        ocr_file.remark = None
        ocr_file.update_at = now
        log.info(
            "paddle ocr success file_id={} layout_cards={} page_count={} log_id={}",
            ocr_file.id,
            len(pages),
            page_total,
            envelope.log_id,
        )
