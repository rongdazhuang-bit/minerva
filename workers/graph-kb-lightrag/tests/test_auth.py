"""API key middleware tests for the LightRAG worker."""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient

_TEST_KEY = "test-lightrag-worker-key"
os.environ["GRAPH_KB_WORKER_FAKE"] = "1"
os.environ["GRAPH_KB_LIGHTRAG_WORKER_API_KEY"] = _TEST_KEY

import app.main as main_mod

_AUTH = {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient against a reloaded app with fake store."""

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_health_does_not_require_api_key(client: TestClient) -> None:
    """GET /health must stay unauthenticated for probes."""

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_without_authorization_returns_401(client: TestClient) -> None:
    """Business endpoints must reject missing Bearer token."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


def test_post_with_wrong_api_key_returns_401(client: TestClient) -> None:
    """Mismatched Bearer token must return 401."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_post_with_valid_api_key_succeeds(client: TestClient) -> None:
    """Valid Bearer token must allow business endpoints."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
