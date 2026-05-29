"""Tests for MinerU file OCR strategy URL mode guards."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.service.strategies.mineru import MineruFileStrategy
from app.sys.tool.ocr.domain.db.models import SysOcrTool


def _ocr_file() -> OcrFile:
    """Minimal ``OcrFile`` row for strategy tests."""
    return OcrFile(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        object_key="uploads/demo.pdf",
        file_name="demo.pdf",
        ocr_type="MINERU",
        status="PROCESS",
    )


def _tool(url: str) -> SysOcrTool:
    """Minimal MinerU tool row."""
    return SysOcrTool(
        workspace_id=uuid.uuid4(),
        name="mineru",
        url=url,
        ocr_type="MINERU",
        ocr_config=None,
    )


@pytest.mark.asyncio
async def test_process_async_url_raises() -> None:
    """``/tasks`` URL fails fast with async-not-implemented."""
    strategy = MineruFileStrategy()
    session = MagicMock()
    with pytest.raises(NotImplementedError, match="mineru_async_not_implemented"):
        await strategy.process(session=session, ocr_file=_ocr_file(), tool=_tool("http://127.0.0.1:8000/tasks"))


@pytest.mark.asyncio
async def test_process_invalid_url_raises() -> None:
    """Unknown path fails with invalid-url remark code."""
    strategy = MineruFileStrategy()
    session = MagicMock()
    with pytest.raises(ValueError, match="mineru_invalid_url_path"):
        await strategy.process(
            session=session,
            ocr_file=_ocr_file(),
            tool=_tool("http://127.0.0.1:8000/health"),
        )


@pytest.mark.asyncio
async def test_process_sync_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path persists one MinerU page row and marks SUCCESS."""
    from pathlib import Path

    fixture = Path(__file__).resolve().parent / "fixtures" / "mineru" / "sample.zip"
    zip_bytes = fixture.read_bytes()

    monkeypatch.setattr(
        "app.file_ocr.service.strategies.mineru.read_workspace_object_bytes",
        AsyncMock(return_value=b"%PDF-1.4"),
    )
    monkeypatch.setattr(
        "app.file_ocr.service.strategies.mineru.post_file_parse",
        AsyncMock(return_value=(zip_bytes, "application/zip")),
    )
    monkeypatch.setattr(
        "app.file_ocr.service.strategies.mineru.rasterize_source_file",
        lambda raw, file_name=None: [b"png"],
    )
    monkeypatch.setattr(
        "app.file_ocr.service.strategies.mineru.upload_page_rasters",
        AsyncMock(return_value={0: "raster/key.png"}),
    )

    session = MagicMock()
    session.execute = AsyncMock()
    added: list[object] = []
    session.add = added.append

    ocr_file = _ocr_file()
    strategy = MineruFileStrategy()
    await strategy.process(
        session=session,
        ocr_file=ocr_file,
        tool=_tool("http://127.0.0.1:8000/file_parse"),
    )

    assert ocr_file.status == "SUCCESS"
    assert ocr_file.page_count == 1
    assert len(added) == 1
