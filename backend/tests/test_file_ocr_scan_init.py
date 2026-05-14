"""Tests for file OCR Celery scan orchestration and Paddle strategy helpers."""

from __future__ import annotations

import os
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.config import settings
from app.core.infrastructure.db.session import async_session_factory
from app.file_ocr.constants import FILE_OCR_LOG_STATUS_FAILED, FILE_OCR_LOG_STATUS_SUCCESS
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_log import OcrFileLog
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.file_ocr.service.ocr_http_headers import build_ocr_tool_http_headers
from app.file_ocr.service.scan_init import run_file_ocr_scan_tick
from app.file_ocr.service.strategies.registry import get_file_ocr_strategy
from app.main import app
from app.ocr.paddleocr.schemas import LayoutParsingApiResponse
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from tests.test_file_ocr_api import _ensure_ocr_file_columns


def _should_skip_db_tests() -> bool:
    """Mirror other DB suites so CI can opt out without Postgres."""

    if os.environ.get("MINERVA_SKIP_DB_TESTS", "").lower() in ("1", "true", "yes"):
        return True
    return False


def _db_skip():
    """Mark async DB tests so sync helpers still run when Postgres is absent."""

    return pytest.mark.skipif(
        _should_skip_db_tests(),
        reason="Set MINERVA_SKIP_DB_TESTS=1 to skip (e.g. CI without Docker Postgres)",
    )


def _workspace_id_from_access_token(access_token: str) -> str:
    """Decode workspace id from auth token payload."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


def test_build_ocr_tool_http_headers_basic() -> None:
    """BASIC auth should emit a single Authorization header."""

    tool = SysOcrTool(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="t",
        url="http://localhost/layout-parsing",
        auth_type="BASIC",
        user_name="user",
        user_passwd="pass",
    )
    headers = build_ocr_tool_http_headers(tool)
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_get_file_ocr_strategy_contains_paddle() -> None:
    """Registry must expose the Paddle adapter under its ``ocr_type`` key."""

    strategy = get_file_ocr_strategy("PADDLE_OCR")
    assert strategy.ocr_type == "PADDLE_OCR"


@pytest.mark.asyncio
@_db_skip()
async def test_scan_marks_failed_when_no_paddle_tool() -> None:
    """Without ``sys_ocr_tool`` rows the worker should mark PROCESS rows as FAILED."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-scan-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        wid = uuid.UUID(workspace_id)
        headers = {"Authorization": f"Bearer {token}"}
        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFilePaddleocr).where(OcrFilePaddleocr.workspace_id == wid))
                await session.execute(delete(OcrFile).where(OcrFile.workspace_id == wid))
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/a.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

    row: OcrFile | None = None
    for _ in range(40):
        async with async_session_factory() as session:
            row = await session.get(OcrFile, ocr_id)
            assert row is not None
            if row.status != "INIT":
                break
        async with async_session_factory() as session:
            await run_file_ocr_scan_tick(session)
    assert row is not None
    assert row.status == "FAILED"
    assert row.remark is not None
    assert "no_sys_ocr_tool" in row.remark
    async with async_session_factory() as session:
        log_rows = (
            await session.execute(select(OcrFileLog).where(OcrFileLog.ocr_file_id == ocr_id))
        ).scalars().all()
    assert len(log_rows) == 1
    assert log_rows[0].status == FILE_OCR_LOG_STATUS_FAILED
    assert log_rows[0].finish_at is not None
    assert log_rows[0].remark is not None


@pytest.mark.asyncio
@_db_skip()
async def test_scan_paddle_success_with_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: mock S3 bytes and Paddle HTTP, assert SUCCESS and one result row."""

    await _ensure_ocr_file_columns()

    async def _fake_read(_session: object, *, workspace_id: uuid.UUID, object_key: str) -> bytes:
        del workspace_id, object_key
        return b"%PDF-1.4"

    async def _fake_post(
        url: str,
        body: object,
        *,
        client: object | None = None,
        headers: object | None = None,
        timeout: object | None = None,
        exclude_none: bool = True,
    ) -> LayoutParsingApiResponse:
        del url, body, client, headers, timeout, exclude_none
        return LayoutParsingApiResponse.model_validate(
            {
                "logId": "test-log",
                "errorCode": 0,
                "errorMsg": "",
                "result": {
                    "layoutParsingResults": [
                        {"markdown": {"text": "# Title", "images": {"a": "b"}}},
                    ],
                    "dataInfo": {"numPages": 12},
                },
            }
        )

    monkeypatch.setattr(
        "app.file_ocr.service.strategies.paddle.read_workspace_object_bytes",
        _fake_read,
    )
    monkeypatch.setattr(
        "app.file_ocr.service.strategies.paddle.post_layout_parsing",
        _fake_post,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-scan-ok-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        wid = uuid.UUID(workspace_id)
        headers = {"Authorization": f"Bearer {token}"}
        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFilePaddleocr).where(OcrFilePaddleocr.workspace_id == wid))
                await session.execute(delete(OcrFile).where(OcrFile.workspace_id == wid))
        tool_body = {
            "name": "paddle-local",
            "url": "http://127.0.0.1:9999/layout-parsing",
            "auth_type": "NONE",
            "ocr_type": "PADDLE_OCR",
        }
        tool_resp = await ac.post(
            f"/workspaces/{workspace_id}/ocr-tools",
            headers=headers,
            json=tool_body,
        )
        assert tool_resp.status_code == 201, tool_resp.text
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/b.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

    row: OcrFile | None = None
    for _ in range(40):
        async with async_session_factory() as session:
            row = await session.get(OcrFile, ocr_id)
            assert row is not None
            if row.status == "SUCCESS":
                break
        async with async_session_factory() as session:
            await run_file_ocr_scan_tick(session)
    assert row is not None
    assert row.status == "SUCCESS"
    assert row.page_count == 12
    async with async_session_factory() as session:
        res = await session.execute(
            select(OcrFilePaddleocr).where(OcrFilePaddleocr.file_id == ocr_id)
        )
        pages = list(res.scalars().all())
    assert len(pages) == 1
    assert pages[0].markdown_text == "# Title"
    async with async_session_factory() as session:
        log_rows = (
            await session.execute(select(OcrFileLog).where(OcrFileLog.ocr_file_id == ocr_id))
        ).scalars().all()
    assert len(log_rows) == 1
    assert log_rows[0].status == FILE_OCR_LOG_STATUS_SUCCESS
    assert log_rows[0].page_count == 12
    assert log_rows[0].finish_at is not None


@pytest.mark.asyncio
@_db_skip()
async def test_scan_skips_mineru_init_rows() -> None:
    """MINERU tasks stay INIT because they are excluded from the scan allowlist."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-mineru-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        wid = uuid.UUID(workspace_id)
        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFilePaddleocr).where(OcrFilePaddleocr.workspace_id == wid))
                await session.execute(delete(OcrFile).where(OcrFile.workspace_id == wid))
        payload = {
            "ocr_type": "MINERU",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/c.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

    async with async_session_factory() as session:
        await run_file_ocr_scan_tick(session)
    async with async_session_factory() as session:
        row = await session.get(OcrFile, ocr_id)
        assert row is not None
        assert row.status == "INIT"
