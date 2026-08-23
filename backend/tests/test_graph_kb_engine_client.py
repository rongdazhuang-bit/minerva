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
