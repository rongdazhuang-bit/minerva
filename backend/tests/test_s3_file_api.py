"""Integration tests for workspace S3 file APIs with monkeypatched gateway."""

from __future__ import annotations

import io
import re
import uuid
from datetime import UTC, datetime

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.s3.domain.models import S3DownloadProxy, S3ObjectItem, S3StorageConfig
from app.s3.infrastructure.s3_gateway import S3Gateway
from app.s3.service import s3_file_service as s3_service_module

# In-memory bucket/object store used by fake S3 gateway for tests.
_FAKE_S3_STORE: dict[str, dict[str, bytes]] = {}


class _FakeS3Gateway:
    """Simple in-memory implementation of ``S3Gateway`` used in tests."""

    def upload_object(
        self,
        *,
        bucket: str,
        object_key: str,
        payload: bytes,
        content_type: str | None,
    ) -> None:
        """Persist uploaded object bytes in test-local memory."""

        del content_type
        _FAKE_S3_STORE.setdefault(bucket, {})[object_key] = payload

    def list_objects(self, *, bucket: str, prefix: str) -> list[S3ObjectItem]:
        """List fake objects under one prefix in lexical key order."""

        bucket_items = _FAKE_S3_STORE.get(bucket, {})
        keys = sorted(k for k in bucket_items if k.startswith(prefix))
        now = datetime.now(UTC)
        return [
            S3ObjectItem(object_key=key, size=len(bucket_items[key]), last_modified=now)
            for key in keys
        ]

    def create_presigned_download_url(
        self, *, bucket: str, object_key: str, expires_in: int
    ) -> str:
        """Return deterministic fake presigned URL for assertions."""

        return f"https://fake-s3.local/{bucket}/{object_key}?exp={expires_in}"

    def open_download_stream(self, *, bucket: str, object_key: str) -> S3DownloadProxy:
        """Return stream payload or raise not-found error via AppError mapping path."""

        payload = _FAKE_S3_STORE.get(bucket, {}).get(object_key)
        if payload is None:
            from app.exceptions import AppError

            raise AppError("s3.object_not_found", "S3 object not found", 404)
        return S3DownloadProxy(
            stream=io.BytesIO(payload),
            content_type="application/octet-stream",
            content_length=len(payload),
        )

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        """Delete one fake object or raise not-found when missing."""

        payload = _FAKE_S3_STORE.get(bucket, {})
        if object_key not in payload:
            from app.exceptions import AppError

            raise AppError("s3.object_not_found", "S3 object not found", 404)
        del payload[object_key]


def _workspace_id_from_access_token(access_token: str) -> str:
    """Extract workspace id from JWT access token for test API calls."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


def _fake_gateway_factory(config: S3StorageConfig) -> S3Gateway:
    """Build fake gateway while ensuring test bucket namespace exists."""

    _FAKE_S3_STORE.setdefault(config.bucket, {})
    return _FakeS3Gateway()


@pytest.fixture(autouse=True)
def _patch_s3_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch gateway factory to avoid external S3 network calls."""

    _FAKE_S3_STORE.clear()
    monkeypatch.setattr(s3_service_module, "create_s3_gateway", _fake_gateway_factory)


@pytest.mark.asyncio
async def test_s3_file_upload_list_download_delete_and_isolation() -> None:
    """Cover main S3 file lifecycle and workspace isolation."""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        user1_email = f"s3u1-{uuid.uuid4().hex}@example.com"
        user2_email = f"s3u2-{uuid.uuid4().hex}@example.com"
        password = "secret1234"

        reg1 = await ac.post("/auth/register", json={"email": user1_email, "password": password})
        assert reg1.status_code == 201, reg1.text
        token1 = reg1.json()["access_token"]
        workspace1 = _workspace_id_from_access_token(token1)

        reg2 = await ac.post("/auth/register", json={"email": user2_email, "password": password})
        assert reg2.status_code == 201, reg2.text
        token2 = reg2.json()["access_token"]

        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        storage_create = await ac.post(
            f"/workspaces/{workspace1}/file-storages",
            headers=headers1,
            json={
                "name": "bucket-ws1",
                "type": "S3",
                "enabled": True,
                "auth_type": "BASIC",
                "endpoint_url": "http://fake-s3.local",
                "auth_name": "ak",
                "auth_passwd": "sk",
            },
        )
        assert storage_create.status_code == 201, storage_create.text

        upload = await ac.post(
            f"/workspaces/{workspace1}/s3/files:upload?module_prefix=docs",
            headers=headers1,
            files={"file": ("hello.txt", b"hello-s3", "text/plain")},
        )
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()
        object_key = upload_body["object_key"]
        assert re.match(
            r"^docs/\d{4}/\d{2}/[0-9a-f-]{36}\.txt$",
            object_key,
        )

        listed = await ac.get(f"/workspaces/{workspace1}/s3/files?page=1&page_size=10", headers=headers1)
        assert listed.status_code == 200, listed.text
        listed_body = listed.json()
        assert listed_body["total"] == 1
        assert listed_body["items"][0]["object_key"] == object_key

        redirected = await ac.get(
            f"/workspaces/{workspace1}/s3/files:download?object_key={object_key}",
            headers=headers1,
        )
        assert redirected.status_code == 302
        assert redirected.headers["location"].startswith("https://fake-s3.local/bucket-ws1/")

        proxied = await ac.get(
            f"/workspaces/{workspace1}/s3/files:download?object_key={object_key}&mode=proxy",
            headers=headers1,
        )
        assert proxied.status_code == 200
        assert proxied.content == b"hello-s3"

        deleted = await ac.delete(
            f"/workspaces/{workspace1}/s3/files?object_key={object_key}",
            headers=headers1,
        )
        assert deleted.status_code == 204

        listed_after_delete = await ac.get(
            f"/workspaces/{workspace1}/s3/files?page=1&page_size=10",
            headers=headers1,
        )
        assert listed_after_delete.status_code == 200
        assert listed_after_delete.json()["total"] == 0

        forbidden = await ac.get(f"/workspaces/{workspace1}/s3/files?page=1&page_size=10", headers=headers2)
        assert forbidden.status_code == 403
