"""Tests for GraphKB engine client protocol, Fake, modes, and HTTP adapter."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.exceptions import AppError
from app.graph_kb.domain.constants import ENGINE_GRAPHRAG, ENGINE_LIGHTRAG, QUERY_NAIVE
from app.graph_kb.engine.fake_client import FakeGraphEngineClient
from app.graph_kb.engine.http_client import HttpGraphEngineClient
from app.graph_kb.engine.modes import map_query_mode
from app.graph_kb.engine.types import (
    ModelEndpoint,
    WorkerDocument,
    WorkerIndexRequest,
    WorkerQueryRequest,
)


def test_graphrag_rejects_naive() -> None:
    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_GRAPHRAG, QUERY_NAIVE)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fake_index_isolated_by_graph() -> None:
    client = FakeGraphEngineClient()
    llm = ModelEndpoint("http://x", "k", "m")
    a = uuid4()
    b = uuid4()
    w = uuid4()
    req_a = WorkerIndexRequest(
        workspace_id=w,
        graph_id=a,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "a.txt", "alpha")],
        llm=llm,
        embedding=llm,
    )
    req_b = WorkerIndexRequest(
        workspace_id=w,
        graph_id=b,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "b.txt", "beta")],
        llm=llm,
        embedding=llm,
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
    llm = ModelEndpoint("http://x", "k", "m")
    w1, w2, g = uuid4(), uuid4(), uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w1,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "a.txt", "secret-w1")],
            llm=llm,
            embedding=llm,
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
    llm = ModelEndpoint("http://llm", "key", "model")
    w = uuid4()
    g = uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "d.txt", "hello")],
            llm=llm,
            embedding=llm,
        )
    )
    body = captured["body"]
    assert body["workspace_id"] == str(w)
    assert body["graph_id"] == str(g)
    assert "lightrag_workspace" not in body
    assert "workspace" not in body


@pytest.mark.asyncio
async def test_http_query_payload_includes_llm_embedding() -> None:
    """Query JSON must send Chat/Embeddings credentials when present."""

    import json

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"answer": "ok", "citations": []})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    llm = ModelEndpoint("http://llm", "llm-key", "chat-m")
    emb = ModelEndpoint("http://emb", "emb-key", "emb-m")
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
            llm=llm,
            embedding=emb,
        )
    )
    body = captured["body"]
    assert body["llm"] == {"base_url": "http://llm", "api_key": "llm-key", "model": "chat-m"}
    assert body["embedding"] == {
        "base_url": "http://emb",
        "api_key": "emb-key",
        "model": "emb-m",
    }


@pytest.mark.asyncio
async def test_fake_query_works_without_model_endpoints() -> None:
    """Fake client must accept query requests that omit llm/embedding."""

    client = FakeGraphEngineClient()
    w, g = uuid4(), uuid4()
    result = await client.query(
        WorkerQueryRequest(w, g, ENGINE_LIGHTRAG, "plain", "local", 5)
    )
    assert result.answer.startswith("fake:")
