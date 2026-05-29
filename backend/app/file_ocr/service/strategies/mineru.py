"""MinerU strategy: S3 source fetch, ``/file_parse`` HTTP call, ``ocr_file_mineru`` rows."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFileMineru
from app.file_ocr.service.mineru_ocr_request import (
    build_file_parse_form_for_tool,
    resolve_mineru_url_mode,
)
from app.file_ocr.service.mineru_result_parse import parse_mineru_response
from app.file_ocr.service.ocr_http_headers import build_ocr_tool_http_headers
from app.file_ocr.service.s3_object_bytes import read_workspace_object_bytes
from app.layout.page_raster import rasterize_source_file, upload_page_rasters
from app.ocr.mineru.client import post_file_parse
from app.sys.tool.ocr.domain.db.models import SysOcrTool

from .base import FileOcrEngineStrategy

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC ``datetime`` for ORM timestamps."""
    return datetime.now(UTC)


class MineruFileStrategy(FileOcrEngineStrategy):
    """Calls MinerU ``/file_parse`` and stores markdown fragments per page."""

    ocr_type: ClassVar[str] = "MINERU"

    async def process(
        self,
        *,
        session: AsyncSession,
        ocr_file: OcrFile,
        tool: SysOcrTool,
    ) -> None:
        """Download the source object, invoke MinerU file_parse, then persist per-page markdown."""
        url = (tool.url or "").strip()
        if not url:
            raise ValueError("empty MinerU tool url")

        mode = resolve_mineru_url_mode(url)
        if mode == "async":
            raise NotImplementedError("file_ocr:mineru_async_not_implemented")
        if mode == "invalid":
            raise ValueError("file_ocr:mineru_invalid_url_path")

        raw = await read_workspace_object_bytes(
            session,
            workspace_id=ocr_file.workspace_id,
            object_key=ocr_file.object_key,
        )
        file_name = (ocr_file.file_name or ocr_file.object_key.rsplit("/", maxsplit=1)[-1]).strip()
        form_data = build_file_parse_form_for_tool(tool)
        headers = build_ocr_tool_http_headers(tool)
        body, content_type = await post_file_parse(
            url,
            file_name=file_name,
            file_bytes=raw,
            form_data=form_data,
            headers=headers or None,
        )
        pages = parse_mineru_response(body=body, content_type=content_type)

        page_pngs = rasterize_source_file(raw, file_name=ocr_file.file_name)
        raster_keys = await upload_page_rasters(
            session,
            workspace_id=ocr_file.workspace_id,
            ocr_file_id=ocr_file.id,
            page_pngs=page_pngs,
        )

        await session.execute(
            delete(OcrFileMineru).where(
                OcrFileMineru.workspace_id == ocr_file.workspace_id,
                OcrFileMineru.file_id == ocr_file.id,
            )
        )
        now = _utc_now()
        for page in pages:
            images_json = (
                json.dumps(page.markdown_images, ensure_ascii=False)
                if page.markdown_images
                else None
            )
            session.add(
                OcrFileMineru(
                    id=uuid.uuid4(),
                    workspace_id=ocr_file.workspace_id,
                    file_id=ocr_file.id,
                    page_index=page.page_index,
                    markdown_text=page.markdown_text,
                    markdown_images=images_json,
                    page_width=page.page_width,
                    page_height=page.page_height,
                    layout_blocks_json=None,
                    page_raster_object_key=raster_keys.get(page.page_index or 0),
                    layout_version=settings.layout_schema_version,
                    create_at=now,
                    update_at=now,
                )
            )

        ocr_file.page_count = len(pages) if pages else len(page_pngs)
        ocr_file.status = "SUCCESS"
        ocr_file.remark = None
        ocr_file.update_at = now
        _LOGGER.info(
            "mineru ocr success file_id=%s pages=%s page_count=%s",
            ocr_file.id,
            len(pages),
            ocr_file.page_count,
        )
