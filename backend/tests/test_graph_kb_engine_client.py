"""Tests for GraphKB engine client protocol, Fake, modes, and HTTP adapter."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    ENGINE_GRAPHRAG,
    ENGINE_LIGHTRAG,
    QUERY_BASIC,
    QUERY_NAIVE,
)
from app.graph_kb.engine.fake_client import FakeGraphEngineClient
from app.graph_kb.engine.http_client import HttpGraphEngineClient
from app.graph_kb.engine.modes import map_query_mode
from app.graph_kb.engine.types import (
    WorkerDocument,
    WorkerIndexRequest,
    WorkerQueryRequest,
)


def test_graphrag_rejects_naive() -> None:
    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_GRAPHRAG, QUERY_NAIVE)
    assert exc.value.status_code == 400


def test_graphrag_accepts_basic() -> None:
    """GraphRAG must accept unified mode basic (Basic Search)."""

    assert map_query_mode(ENGINE_GRAPHRAG, QUERY_BASIC) == QUERY_BASIC


def test_lightrag_rejects_basic() -> None:
    """LightRAG has no basic mode; map_query_mode must 400."""

    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_LIGHTRAG, QUERY_BASIC)
    assert exc.value.status_code == 400
    assert exc.value.code == "graph_kb.invalid_mode"


@pytest.mark.asyncio
async def test_fake_index_isolated_by_graph() -> None:
    client = FakeGraphEngineClient()
    a = uuid4()
    b = uuid4()
    w = uuid4()
    req_a = WorkerIndexRequest(
        workspace_id=w,
        graph_id=a,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "a.txt", "alpha")],
    )
    req_b = WorkerIndexRequest(
        workspace_id=w,
        graph_id=b,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "b.txt", "beta")],
    )
    await client.index(req_a)
    await client.index(req_b)
    qa = await client.query(
        WorkerQueryRequest(w, a, ENGINE_LIGHTRAG, "q", "local", 5)
    )
    assert "alpha" in qa.answer or qa.answer.startswith("fake:")
    export_b = await client.export_graph(engine=ENGINE_LIGHTRAG, workspace_id=w, graph_id=b)
    names = {e["name"] for e in export_b.entities}
    assert "alpha" not in names


@pytest.mark.asyncio
async def test_cross_workspace_export_empty() -> None:
    """Same graph_id in another workspace must not see indexed entities."""

    client = FakeGraphEngineClient()
    w1, w2, g = uuid4(), uuid4(), uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w1,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "a.txt", "secret-w1")],
        )
    )
    export = await client.export_graph(
        engine=ENGINE_LIGHTRAG, workspace_id=w2, graph_id=g
    )
    assert export.entities == []


@pytest.mark.asyncio
async def test_http_index_payload_has_no_lightrag_workspace() -> None:
    """HTTP JSON must send workspace_id + graph_id only, never a pre-built workspace string."""

    import json

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"entities": [], "relations": []})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    w = uuid4()
    g = uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "d.txt", "hello")],
        )
    )
    body = captured["body"]
    assert body["workspace_id"] == str(w)
    assert body["graph_id"] == str(g)
    assert "lightrag_workspace" not in body
    assert "workspace" not in body
    assert "llm" not in body
    assert "embedding" not in body


@pytest.mark.asyncio
async def test_http_query_payload_omits_llm_embedding() -> None:
    """Query JSON must not send Chat/Embeddings credentials (worker env only)."""

    import json

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"answer": "ok", "citations": []})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    w = uuid4()
    g = uuid4()
    await client.query(
        WorkerQueryRequest(
            workspace_id=w,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            query="hello",
            mode="hybrid",
            top_k=5,
        )
    )
    body = captured["body"]
    assert "llm" not in body
    assert "embedding" not in body


@pytest.mark.asyncio
async def test_fake_query_works_without_model_endpoints() -> None:
    """Fake client must accept query requests without llm/embedding."""

    client = FakeGraphEngineClient()
    w, g = uuid4(), uuid4()
    result = await client.query(
        WorkerQueryRequest(w, g, ENGINE_LIGHTRAG, "plain", "local", 5)
    )
    assert result.answer.startswith("fake:")


@pytest.mark.asyncio
async def test_http_post_includes_authorization_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outbound worker calls must send Authorization: Bearer with engine-specific key."""

    from app.config import settings

    monkeypatch.setattr(settings, "graph_kb_lightrag_worker_api_key", "lightrag-secret")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"entities": [], "relations": []})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    w, g = uuid4(), uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "d.txt", "hello")],
        )
    )
    assert captured["authorization"] == "Bearer lightrag-secret"


@pytest.mark.asyncio
async def test_http_worker_401_maps_to_unauthorized_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker HTTP 401 must map to graph_kb.worker_unauthorized."""

    from app.config import settings

    monkeypatch.setattr(settings, "graph_kb_lightrag_worker_api_key", "k")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    with pytest.raises(AppError) as exc:
        await client.export_graph(
            engine=ENGINE_LIGHTRAG, workspace_id=uuid4(), graph_id=uuid4()
        )
    assert exc.value.code == "graph_kb.worker_unauthorized"
    assert exc.value.status_code == 502
