from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import settings
from app.file_ocr.api.schemas import OcrFileListItemOut
from app.core.infrastructure.db.session import engine
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
    await _ensure_ocr_file_log_schema()


async def _ensure_ocr_file_log_schema() -> None:
    """Recreate ``ocr_file_log`` in the test DB so the layout always matches the ORM."""

    create_sql = """
    CREATE TABLE ocr_file_log (
        id UUID PRIMARY KEY,
        workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        ocr_file_id UUID NOT NULL REFERENCES ocr_file(id) ON DELETE CASCADE,
        ocr_type VARCHAR(16) NOT NULL,
        status VARCHAR(16) NOT NULL,
        page_count INTEGER NULL,
        remark TEXT NULL,
        start_at TIMESTAMPTZ NOT NULL,
        finish_at TIMESTAMPTZ NULL
    );
    """
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_ocr_file_log_workspace_id ON ocr_file_log (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_ocr_file_log_ocr_file_id ON ocr_file_log (ocr_file_id)",
        "CREATE INDEX IF NOT EXISTS ix_ocr_file_log_file_start ON ocr_file_log (ocr_file_id, start_at)",
    ]
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS ocr_file_log CASCADE"))
        await conn.execute(text(create_sql))
        for stmt in indexes:
            await conn.execute(text(stmt))


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


@pytest.mark.asyncio
async def test_delete_ocr_file_removes_row() -> None:
    """DELETE should remove the task when id belongs to the workspace."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-del-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/04/a.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

        deleted = await ac.delete(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}",
            headers=headers,
        )
        assert deleted.status_code == 204, deleted.text

        again = await ac.delete(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}",
            headers=headers,
        )
        assert again.status_code == 404, again.text


@pytest.mark.asyncio
async def test_retry_ocr_file_sets_init_and_clears_page_count() -> None:
    """POST retry should flip SUCCESS back to INIT, clear remark/page_count, and drop paddle rows."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-retry-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/a.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ocr_file SET status = 'SUCCESS', page_count = 3, remark = 'x' "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": ocr_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO ocr_file_paddleocr (id, workspace_id, file_id, page_index, markdown_text) "
                    "VALUES (gen_random_uuid(), CAST(:wid AS uuid), CAST(:fid AS uuid), 0, 'stale')"
                ),
                {"wid": workspace_id, "fid": ocr_id},
            )

        retry = await ac.post(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/retry",
            headers=headers,
        )
        assert retry.status_code == 200, retry.text
        body = retry.json()
        assert body["status"] == "INIT"
        assert body["page_count"] is None

        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT remark FROM ocr_file WHERE id = CAST(:id AS uuid)"),
                    {"id": ocr_id},
                )
            ).fetchone()
        assert row is not None and row[0] is None

        async with engine.connect() as conn:
            paddle_n = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*)::int FROM ocr_file_paddleocr WHERE file_id = CAST(:fid AS uuid)"
                    ),
                    {"fid": ocr_id},
                )
            ).scalar_one()
        assert int(paddle_n or 0) == 0


@pytest.mark.asyncio
async def test_retry_ocr_file_deletes_mineru_result_rows() -> None:
    """POST retry should remove existing ``ocr_file_mineru`` rows for MINERU tasks."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-retry-mu-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "MINERU",
            "files": [
                {"file_name": "m.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/m.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ocr_file SET status = 'SUCCESS', page_count = 1 "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": ocr_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO ocr_file_mineru (id, workspace_id, file_id, page_index, markdown_text) "
                    "VALUES (gen_random_uuid(), CAST(:wid AS uuid), CAST(:fid AS uuid), 0, 'stale')"
                ),
                {"wid": workspace_id, "fid": ocr_id},
            )

        retry = await ac.post(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/retry",
            headers=headers,
        )
        assert retry.status_code == 200, retry.text

        async with engine.connect() as conn:
            mineru_n = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*)::int FROM ocr_file_mineru WHERE file_id = CAST(:fid AS uuid)"
                    ),
                    {"fid": ocr_id},
                )
            ).scalar_one()
        assert int(mineru_n or 0) == 0


@pytest.mark.asyncio
async def test_list_ocr_file_logs_empty_and_not_found() -> None:
    """GET logs returns an empty page for a valid task and 404 for an unknown id."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-logs-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/logs.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

        listed = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{ocr_id}/logs?page=1&page_size=10",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] == 0
        assert body["items"] == []

        missing = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/{uuid.uuid4()}/logs",
            headers=headers,
        )
        assert missing.status_code == 404, missing.text
