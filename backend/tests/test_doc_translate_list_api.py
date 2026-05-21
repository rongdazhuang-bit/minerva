"""Integration tests for paginated document translation job list API."""

from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.core.infrastructure.db.session import async_session_factory
from app.main import app
from app.translate.domain.constants import (
    DOC_TRANSLATE_STATUS_FAILED,
    DOC_TRANSLATE_STATUS_PENDING,
    DOC_TRANSLATE_STATUS_SUCCESS,
)
from app.translate.infrastructure import repository as translate_repo


def _workspace_id_from_access_token(access_token: str) -> str:
    """Decode workspace id from auth token payload."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


async def _register_workspace_user(ac: AsyncClient) -> tuple[str, str, dict[str, str]]:
    """Create one user/workspace and return token, workspace id, headers."""

    email = f"tr-list-{uuid.uuid4().hex}@example.com"
    reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    workspace_id = _workspace_id_from_access_token(token)
    return token, workspace_id, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_translate_jobs_returns_items_and_total() -> None:
    """List endpoint should return offset pagination shape."""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        _, workspace_id, headers = await _register_workspace_user(ac)
        resp = await ac.get(
            f"/workspaces/{workspace_id}/translate/jobs?page=1&page_size=10",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)
        assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_translate_jobs_filters_by_status() -> None:
    """List endpoint should filter rows by status query param."""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        _, workspace_id, headers = await _register_workspace_user(ac)
        ws_uuid = uuid.UUID(workspace_id)
        model_id = uuid.uuid4()
        async with async_session_factory() as session:
            await translate_repo.create_doc_translate_job(
                session,
                workspace_id=ws_uuid,
                created_by=None,
                title="ok.docx",
                file_name="ok.docx",
                file_ext="docx",
                source_lang="en",
                target_lang="zh-CN",
                model_id=model_id,
                status=DOC_TRANSLATE_STATUS_SUCCESS,
                source_object_key="translate/test/ok.docx",
            )
            await translate_repo.create_doc_translate_job(
                session,
                workspace_id=ws_uuid,
                created_by=None,
                title="fail.pdf",
                file_name="fail.pdf",
                file_ext="pdf",
                source_lang="en",
                target_lang="zh-CN",
                model_id=model_id,
                status=DOC_TRANSLATE_STATUS_FAILED,
                source_object_key="translate/test/fail.pdf",
            )
            await session.commit()

        resp = await ac.get(
            f"/workspaces/{workspace_id}/translate/jobs?status={DOC_TRANSLATE_STATUS_SUCCESS}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["status"] == DOC_TRANSLATE_STATUS_SUCCESS
        assert body["items"][0]["file_name"] == "ok.docx"


@pytest.mark.asyncio
async def test_list_translate_jobs_filters_by_file_name() -> None:
    """List endpoint should apply case-insensitive file_name substring filter."""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        _, workspace_id, headers = await _register_workspace_user(ac)
        ws_uuid = uuid.UUID(workspace_id)
        model_id = uuid.uuid4()
        async with async_session_factory() as session:
            await translate_repo.create_doc_translate_job(
                session,
                workspace_id=ws_uuid,
                created_by=None,
                title="report",
                file_name="Annual_Report.docx",
                file_ext="docx",
                source_lang="en",
                target_lang="zh-CN",
                model_id=model_id,
                status=DOC_TRANSLATE_STATUS_PENDING,
                source_object_key="translate/test/report.docx",
            )
            await translate_repo.create_doc_translate_job(
                session,
                workspace_id=ws_uuid,
                created_by=None,
                title="notes",
                file_name="notes.txt",
                file_ext="txt",
                source_lang="en",
                target_lang="zh-CN",
                model_id=model_id,
                status=DOC_TRANSLATE_STATUS_PENDING,
                source_object_key="translate/test/notes.txt",
            )
            await session.commit()

        resp = await ac.get(
            f"/workspaces/{workspace_id}/translate/jobs?file_name=report",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["file_name"] == "Annual_Report.docx"
