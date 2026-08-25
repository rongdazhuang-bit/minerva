"""Root path must match Minerva backend; custom ``root`` must be rejected."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import pytest

# Load worker test profile before importing app (see backend/workers/graph-kb-graphrag/.env.test).
os.environ["WORKER_ENV"] = "test"
_TEST_KEY = "test-graphrag-worker-key"
os.environ["GRAPH_KB_GRAPHRAG_WORKER_API_KEY"] = _TEST_KEY
_AUTH = {"Authorization": f"Bearer {_TEST_KEY}"}


def _reload_app_modules() -> None:
    """Reload worker modules so ``Settings`` picks up patched environment variables."""

    import importlib

    import app.auth as auth_mod
    import app.config as config_mod
    import app.main as main_mod
    import app.store as store_mod

    importlib.reload(config_mod)
    importlib.reload(store_mod)
    importlib.reload(auth_mod)
    importlib.reload(main_mod)
    return main_mod


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
    main_mod = _reload_app_modules()
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
    resp = client.post("/index", json=payload, headers=_AUTH)
    assert resp.status_code == 400
    assert "root" in resp.text.lower() or "root" in str(resp.json()).lower()


def test_fake_index_writes_fake_json_and_delete_removes_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake mode creates ``{root}/fake.json``; delete_namespace removes the silo."""

    monkeypatch.setenv("GRAPH_KB_DATA", str(tmp_path))
    main_mod = _reload_app_modules()
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
    }
    indexed = client.post("/index", json=payload, headers=_AUTH)
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
        headers=_AUTH,
    )
    assert queried.status_code == 200
    assert queried.json()["answer"] == "fake:alpha"

    basic = client.post(
        "/query",
        json={
            "workspace_id": str(wid),
            "graph_id": str(gid),
            "engine": "graphrag",
            "query": "q",
            "mode": "basic",
            "top_k": 5,
        },
        headers=_AUTH,
    )
    assert basic.status_code == 200
    assert basic.json()["answer"].startswith("fake:")

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
        headers=_AUTH,
    )
    assert naive.status_code == 400

    exported = client.post(
        "/export_graph",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
        headers=_AUTH,
    )
    assert exported.status_code == 200
    assert exported.json()["entities"][0]["id"].startswith("ent-")

    summaries = client.post(
        "/list_summaries",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
        headers=_AUTH,
    )
    assert summaries.status_code == 200
    assert len(summaries.json()["summaries"]) == 1

    deleted = client.post(
        "/delete_namespace",
        json={"workspace_id": str(wid), "graph_id": str(gid), "engine": "graphrag"},
        headers=_AUTH,
    )
    assert deleted.status_code == 204
    assert not root.exists()


@pytest.mark.asyncio
async def test_fake_index_wipes_input_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake reindex must drop leftover input/output before writing current files."""

    monkeypatch.setenv("GRAPH_KB_DATA", str(tmp_path))
    import importlib

    import app.config as config_mod
    import app.store as store_mod

    importlib.reload(config_mod)
    importlib.reload(store_mod)
    from app.namespace import graphrag_root
    from app.store import FakeStore

    store = FakeStore()
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    root = graphrag_root(tmp_path, wid, gid)
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir(parents=True)
    (root / "input" / "old.txt").write_text("stale", encoding="utf-8")
    (root / "output" / "old.parquet").write_text("stale", encoding="utf-8")

    await store.index(
        workspace_id=wid,
        graph_id=gid,
        documents=[
            {
                "document_id": str(UUID("33333333-3333-3333-3333-333333333333")),
                "name": "doc.txt",
                "text": "fresh",
            }
        ],
    )
    assert not (root / "input").exists()
    assert not (root / "output").exists()
    assert (root / "fake.json").is_file()


@pytest.mark.asyncio
async def test_real_index_wipes_and_writes_settings_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real GraphRAG index writes settings.yaml from worker env after wiping silos."""

    import subprocess

    monkeypatch.setenv("GRAPH_KB_DATA", str(tmp_path))
    monkeypatch.setenv("GRAPH_KB_LLM_BASE_URL", "http://llm")
    monkeypatch.setenv("GRAPH_KB_LLM_API_KEY", "sk-llm")
    monkeypatch.setenv("GRAPH_KB_LLM_MODEL", "gpt-test")
    monkeypatch.setenv("GRAPH_KB_EMBEDDING_BASE_URL", "http://emb")
    monkeypatch.setenv("GRAPH_KB_EMBEDDING_API_KEY", "sk-emb")
    monkeypatch.setenv("GRAPH_KB_EMBEDDING_MODEL", "emb-test")
    import importlib

    import app.config as config_mod
    import app.store as store_mod

    importlib.reload(config_mod)
    importlib.reload(store_mod)
    from app.namespace import graphrag_root
    from app.store import GraphRAGStore

    store = GraphRAGStore()
    wid = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    gid = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    root = graphrag_root(tmp_path, wid, gid)
    (root / "input").mkdir(parents=True)
    (root / "output").mkdir(parents=True)
    (root / "input" / "old.txt").write_text("stale", encoding="utf-8")
    (root / "output" / "old.parquet").write_text("stale", encoding="utf-8")

    ran: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        ran.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    await store.index(
        workspace_id=wid,
        graph_id=gid,
        documents=[
            {
                "document_id": str(UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
                "name": "doc.txt",
                "text": "hello",
            }
        ],
    )

    assert not (root / "input" / "old.txt").exists()
    assert not (root / "output").exists()
    settings_text = (root / "settings.yaml").read_text(encoding="utf-8")
    assert "sk-llm" in settings_text
    assert "gpt-test" in settings_text
    assert "sk-emb" in settings_text
    assert "GRAPH_KB_WORKER_FAKE" in settings_text
    assert any(cmd[:2] == ["graphrag", "index"] for cmd in ran)
