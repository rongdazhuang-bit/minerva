"""Fake-mode HTTP contract tests for the LightRAG worker."""

from __future__ import annotations

import os
from uuid import UUID

os.environ["GRAPH_KB_WORKER_FAKE"] = "1"
os.environ["GRAPH_KB_LIGHTRAG_WORKER_API_KEY"] = "test-lightrag-worker-key"

from fastapi.testclient import TestClient

from app.main import app

_AUTH = {"Authorization": "Bearer test-lightrag-worker-key"}


def test_fake_index_query_export_and_delete_ignore_workspace_field() -> None:
    """POST contract matches HttpGraphEngineClient; extra workspace key ignored."""

    client = TestClient(app)
    wid = str(UUID("11111111-1111-1111-1111-111111111111"))
    gid = str(UUID("22222222-2222-2222-2222-222222222222"))
    payload = {
        "workspace_id": wid,
        "graph_id": gid,
        "engine": "lightrag",
        "workspace": "should-be-ignored",
        "lightrag_workspace": "also-ignored",
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
    indexed = client.post("/index", json=payload, headers=_AUTH)
    assert indexed.status_code == 200
    body = indexed.json()
    assert len(body["entities"]) == 1
    assert len(body["relations"]) == 1

    queried = client.post(
        "/query",
        json={
            "workspace_id": wid,
            "graph_id": gid,
            "engine": "lightrag",
            "query": "q",
            "mode": "hybrid",
            "top_k": 5,
            "workspace": "ignored",
        },
        headers=_AUTH,
    )
    assert queried.status_code == 200
    assert queried.json()["answer"] == "fake:alpha"

    exported = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert exported.status_code == 200
    assert exported.json()["entities"][0]["id"].startswith("ent-")

    summaries = client.post(
        "/list_summaries",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert summaries.status_code == 200
    assert len(summaries.json()["summaries"]) == 1

    deleted = client.post(
        "/delete_namespace",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert deleted.status_code == 204

    after = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert after.json() == {"entities": [], "relations": []}
