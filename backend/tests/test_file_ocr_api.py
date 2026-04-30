from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import settings
from app.file_ocr.api.schemas import OcrFileListItemOut
from app.infrastructure.db.session import engine
from app.main import app


def _workspace_id_from_access_token(access_token: str) -> str:
    """Decode workspace id from auth token payload."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


async def _ensure_ocr_file_columns() -> None:
    """Patch local test DB schema for newly added ocr_file columns."""

    statements = [
        "ALTER TABLE ocr_file ADD COLUMN IF NOT EXISTS file_size BIGINT NULL",
        "ALTER TABLE ocr_file ADD COLUMN IF NOT EXISTS object_key VARCHAR(1024) NULL",
        "ALTER TABLE ocr_file ADD COLUMN IF NOT EXISTS page_count INTEGER NULL",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
        await conn.execute(text("UPDATE ocr_file SET object_key = '' WHERE object_key IS NULL"))
        await conn.execute(text("ALTER TABLE ocr_file ALTER COLUMN object_key SET NOT NULL"))


def test_ocr_file_list_item_schema_has_object_key_and_file_size() -> None:
    """Ensure list schema keeps object key and file size fields."""

    row = OcrFileListItemOut(
        id="00000000-0000-0000-0000-000000000000",
        workspace_id="00000000-0000-0000-0000-000000000000",
        file_name="a.pdf",
        ocr_type="PADDLE_OCR",
        status="INIT",
        file_size=123,
        object_key="ocr/file/a.pdf",
        page_count=None,
        create_at=None,
        update_at=None,
    )
    assert row.object_key == "ocr/file/a.pdf"
    assert row.file_size == 123


@pytest.mark.asyncio
async def test_create_ocr_files_sets_init_status_and_null_page_count() -> None:
    """Creating file OCR rows should default to INIT and null page count."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-create-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 1024, "object_key": "ocr_file/2026/04/a.pdf"}
            ],
        }
        resp = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["total"] == 1
        row = body["items"][0]
        assert row["status"] == "INIT"
        assert row["page_count"] is None
        assert row["file_size"] == 1024
        assert row["object_key"] == "ocr_file/2026/04/a.pdf"


@pytest.mark.asyncio
async def test_ocr_file_list_supports_filters_and_pagination() -> None:
    """List endpoint should filter by file_name/status and paginate."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-list-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/04/a.pdf"},
                {"file_name": "b.pdf", "file_size": 11, "object_key": "ocr_file/2026/04/b.pdf"},
                {"file_name": "c.png", "file_size": 12, "object_key": "ocr_file/2026/04/c.png"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text

        listed = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files?page=1&page_size=2&status=INIT&file_name=.pdf",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] >= 2
        assert len(body["items"]) == 2
        assert all(item["status"] == "INIT" for item in body["items"])
        assert all(str(item["file_name"]).endswith(".pdf") for item in body["items"])
