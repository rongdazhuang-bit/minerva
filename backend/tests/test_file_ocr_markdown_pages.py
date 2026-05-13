"""HTTP tests for ``GET .../ocr-files/{id}/markdown-pages``."""

from __future__ import annotations

import json
import os
import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from app.config import settings
from app.core.infrastructure.db.session import async_session_factory
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_result import OcrFilePaddleocr
from app.main import app
from tests.test_file_ocr_api import _ensure_ocr_file_columns


def _should_skip_db_tests() -> bool:
    """Allow CI without Postgres."""

    if os.environ.get("MINERVA_SKIP_DB_TESTS", "").lower() in ("1", "true", "yes"):
        return True
    return False


_db_skip = pytest.mark.skipif(
    _should_skip_db_tests(),
    reason="Set MINERVA_SKIP_DB_TESTS=1 to skip (e.g. CI without Docker Postgres)",
)


def _workspace_id_from_access_token(access_token: str) -> str:
    """Decode workspace id from auth token payload."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_success_order_and_images() -> None:
    """SUCCESS task returns pages sorted by ``page_index`` with parsed ``images``."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        wid = uuid.UUID(workspace_id)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/a.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

        async with async_session_factory() as session:
            async with session.begin():
                row = await session.get(OcrFile, ocr_id)
                assert row is not None
                row.status = "SUCCESS"
                row.page_count = 2
                session.add(
                    OcrFilePaddleocr(
                        id=uuid.uuid4(),
                        workspace_id=wid,
                        file_id=ocr_id,
                        page_index=1,
                        markdown_text="second",
                        markdown_images=json.dumps({"p1": "http://b"}),
                    )
                )
                session.add(
                    OcrFilePaddleocr(
                        id=uuid.uuid4(),
                        workspace_id=wid,
                        file_id=ocr_id,
                        page_index=0,
                        markdown_text="first",
                        markdown_images=json.dumps({"p0": "http://a"}),
                    )
                )

        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["file_id"] == str(ocr_id)
        assert body["ocr_type"] == "PADDLE_OCR"
        pages = body["pages"]
        assert len(pages) == 2
        assert pages[0]["page_index"] == 0
        assert pages[0]["markdown_text"] == "first"
        assert pages[0]["images"] == {"p0": "http://a"}
        assert pages[1]["page_index"] == 1
        assert pages[1]["images"] == {"p1": "http://b"}

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFilePaddleocr).where(OcrFilePaddleocr.file_id == ocr_id))
                await session.execute(delete(OcrFile).where(OcrFile.id == ocr_id))


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_invalid_images_json_yields_null_images() -> None:
    """Corrupt ``markdown_images`` JSON yields ``images: null`` for that page only."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md2-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        wid = uuid.UUID(workspace_id)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "b.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/b.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

        async with async_session_factory() as session:
            async with session.begin():
                row = await session.get(OcrFile, ocr_id)
                assert row is not None
                row.status = "SUCCESS"
                row.page_count = 1
                session.add(
                    OcrFilePaddleocr(
                        id=uuid.uuid4(),
                        workspace_id=wid,
                        file_id=ocr_id,
                        page_index=0,
                        markdown_text="x",
                        markdown_images="not-json",
                    )
                )

        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        pages = resp.json()["pages"]
        assert len(pages) == 1
        assert pages[0]["images"] is None

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFilePaddleocr).where(OcrFilePaddleocr.file_id == ocr_id))
                await session.execute(delete(OcrFile).where(OcrFile.id == ocr_id))


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_non_success_returns_409() -> None:
    """INIT task should yield 409 for markdown-pages."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md3-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "c.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/c.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ocr_file.detail_requires_success"

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFile).where(OcrFile.id == uuid.UUID(ocr_id)))


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_not_found_returns_404() -> None:
    """Unknown OCR file id returns 404."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md4-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        missing = uuid.uuid4()
        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{missing}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "ocr_file.not_found"


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_unknown_ocr_type_returns_422() -> None:
    """Unsupported ``ocr_type`` on a SUCCESS row yields 422."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md5-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "d.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/d.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(OcrFile)
                    .where(OcrFile.id == ocr_id)
                    .values(ocr_type="ZZ", status="SUCCESS", page_count=0)
                )

        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "ocr_file.unsupported_detail_type"

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFile).where(OcrFile.id == ocr_id))


@pytest.mark.asyncio
@_db_skip()
async def test_markdown_pages_empty_success_returns_empty_pages() -> None:
    """SUCCESS with no result rows returns 200 and ``pages: []``."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-md6-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "e.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/e.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = uuid.UUID(create.json()["items"][0]["id"])

        async with async_session_factory() as session:
            async with session.begin():
                row = await session.get(OcrFile, ocr_id)
                assert row is not None
                row.status = "SUCCESS"
                row.page_count = 0

        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/markdown-pages",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["pages"] == []

        async with async_session_factory() as session:
            async with session.begin():
                await session.execute(delete(OcrFile).where(OcrFile.id == ocr_id))
