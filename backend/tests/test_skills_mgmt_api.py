"""API integration tests for skills-mgmt routes."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from tests.conftest import TEST_WORKSPACE_ID


def _registry_url() -> str:
    return f"/workspaces/{TEST_WORKSPACE_ID}/agent/v2/skills-mgmt/registry"


def _upload_url() -> str:
    return f"/workspaces/{TEST_WORKSPACE_ID}/agent/v2/skills-mgmt/upload"


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_tenant_member_get_registry_forbidden(member_client: TestClient) -> None:
    """Non-admin tenant members receive 403 on registry listing."""

    response = member_client.get(_registry_url())

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "skills.forbidden"


def test_tenant_admin_get_registry_ok(admin_client: TestClient) -> None:
    """Tenant owner/admin can list the skill registry."""

    response = admin_client.get(_registry_url())

    assert response.status_code == 200
    skills = response.json()["skills"]
    assert len(skills) == 1
    assert skills[0]["id"] == "demo"
    assert skills[0]["file_count"] == 1


def test_tenant_admin_upload_zip_appears_in_registry(admin_client: TestClient) -> None:
    """Tenant admin can upload a zip package and see it in the registry."""

    zip_bytes = _make_zip(
        {
            "newskill/SKILL.md": b"# New skill",
            "newskill/tools.py": b"# tools",
        }
    )
    upload = admin_client.post(
        _upload_url(),
        files={"file": ("newskill.zip", zip_bytes, "application/zip")},
    )

    assert upload.status_code == 201
    assert upload.json() == {"skill_id": "newskill"}

    registry = admin_client.get(_registry_url())
    assert registry.status_code == 200
    ids = {row["id"] for row in registry.json()["skills"]}
    assert "newskill" in ids
    newskill = next(row for row in registry.json()["skills"] if row["id"] == "newskill")
    assert newskill["file_count"] == 2
