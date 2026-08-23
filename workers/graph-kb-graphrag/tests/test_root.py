"""Root path must match Minerva backend; custom ``root`` must be rejected."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import pytest

# Fake mode before importing app.main so the worker picks FakeStore.
os.environ["GRAPH_KB_WORKER_FAKE"] = "1"


def test_graphrag_root_nests_workspace_then_graph(tmp_path: Path) -> None:
    """Same UUIDs as Task 1 must yield ``{data_root}/{wid}/{gid}``."""

    from app.namespace import graphrag_root

    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    root = graphrag_root(tmp_path, wid, gid)
    assert root == tmp_path / str(wid) / str(gid)


def test_request_with_root_field_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST bodies must not carry a client-supplied ``root`` path."""

    monkeypatch.setenv("GRAPH_KB_DATA", str(tmp_path))
    # Re-import after env so data root resolves to tmp_path.
    import importlib

    import app.main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    client = TestClient(main_mod.app)
    wid = str(UUID("11111111-1111-1111-1111-111111111111"))
    gid = str(UUID("22222222-2222-2222-2222-222222222222"))
    payload = {
        "workspace_id": wid,
        "graph_id": gid,
        "engine": "graphrag",
        "root": "/evil/path",
        "documents": [
            {
                "document_id": str(UUID("33333333-3333-3333-3333-333333333333")),
                "name": "doc.txt",
                "text": "alpha",
            }
        ],
    }
    resp = client.post("/index", json=payload)
    assert resp.status_code == 400
    assert "root" in resp.text.lower() or "root" in str(resp.json()).lower()


def test_fake_index_writes_fake_json_and_delete_removes_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake mode creates ``{root}/fake.json``; delete_namespace removes the silo."""

    monkeypatch.setenv("GRAPH_KB_DATA", str(tmp_path))
    monkeypatch.setenv("GRAPH_KB_WORKER_FAKE", "1")
    import importlib

    import app.main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    client = TestClient(main_mod.app)
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    payload = {
        "workspace_id": str(wid),
        "graph_id": str(gid),
        "engine": "graphrag",
        "documents": [
            {
                "document_id": str(UUID("33333333-3333-3333-3333-333333333333")),
                "name": "doc.txt",
                "text": "alpha",
            }
        ],
        "llm": {"base_url": "http://x", "api_key": "k", "model": "m"},
        "embedding": {"base_url": "http://x", "api_key": "k", "model": "e"},
    }
    indexed = client.post("/index", json=payload)
    assert indexed.status_code == 200
    body = indexed.json()
    assert len(body["entities"]) == 1
    assert len(body["relations"]) == 1

    root = tmp_path / str(wid) / str(gid)
    fake_path = root / "fake.json"
    assert fake_path.is_file()
    stored = json.loads(fake_path.read_text(encoding="utf-8"))
    assert "entities" in stored

    queried = client.post(
        "/query",
        json={
            "workspace_id": str(wid),
            "graph_id": str(gid),
            "engine": "graphrag",
            "query": "q",
            "mode": "global",
            "top_k": 5,
        },
    )
    assert queried.status_code == 200
    assert queried.json()["answer"] == "fake:alpha"

    naive = client.post(
        "/query",
        json={
            "workspace_id": str(wid),
            "graph_id": str(gid),
            "engine": "graphrag",
            "query": "q",
            "mode": "naive",
            "top_k": 5,
        },
    )
    assert naive.status_code == 400

    exported = client.post(
        "/export_graph",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
    )
    assert exported.status_code == 200
    assert exported.json()["entities"][0]["id"].startswith("ent-")

    summaries = client.post(
        "/list_summaries",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
    )
    assert summaries.status_code == 200
    assert len(summaries.json()["summaries"]) == 1

    deleted = client.post(
        "/delete_namespace",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
    )
    assert deleted.status_code == 204
    assert not root.exists()
