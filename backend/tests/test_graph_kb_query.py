"""GraphKB query readiness, subgraph BFS, and related route surface."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.acl import GraphAclActor
from app.graph_kb.domain.constants import ENGINE_LIGHTRAG, STATUS_COMPLETED, STATUS_PENDING
from app.graph_kb.engine.types import WorkerQueryResult
from app.graph_kb.service.query_service import assert_ready_for_query
from app.graph_kb.service.view_service import GRAPH_VIEW_MAX_NODES, build_subgraph


def test_not_ready() -> None:
    """Pending indexing_status must raise 409 graph_kb.not_ready."""

    try:
        assert_ready_for_query(STATUS_PENDING)
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "graph_kb.not_ready"
    else:
        raise AssertionError("expected 409")


def test_ready_when_completed() -> None:
    """Completed graphs may be queried."""

    assert_ready_for_query(STATUS_COMPLETED)


def test_build_subgraph_hops_one_on_chain() -> None:
    """A→B→C chain with hops=1 from A returns only A,B and the A–B edge."""

    entities = [
        {"id": "A", "name": "a"},
        {"id": "B", "name": "b"},
        {"id": "C", "name": "c"},
    ]
    relations = [
        {"from_id": "A", "to_id": "B", "type": "next"},
        {"from_id": "B", "to_id": "C", "type": "next"},
    ]
    result = build_subgraph(entities, relations, seed_id="A", hops=1, max_nodes=200)
    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids == {"A", "B"}
    assert len(result["edges"]) == 1
    edge = result["edges"][0]
    ends = {edge["from_id"], edge["to_id"]}
    assert ends == {"A", "B"}


def test_graph_view_max_nodes_constant() -> None:
    """Canvas subgraph hard cap must stay at 200."""

    assert GRAPH_VIEW_MAX_NODES == 200


def test_build_subgraph_community_seeds_capped_at_max_nodes() -> None:
    """Community-only view must not exceed max_nodes when seeding members."""

    count = GRAPH_VIEW_MAX_NODES + 50
    entities = [{"id": f"e{i}", "name": f"n{i}"} for i in range(count)]
    community_ids = {f"e{i}" for i in range(count)}
    result = build_subgraph(
        entities,
        [],
        seed_id=None,
        hops=1,
        max_nodes=GRAPH_VIEW_MAX_NODES,
        community_entity_ids=community_ids,
    )
    assert len(result["nodes"]) == GRAPH_VIEW_MAX_NODES


def test_query_and_projection_routes_registered() -> None:
    """Router must expose query, projections, graph-view, index, and job APIs."""

    from app.graph_kb.api.router import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/query" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/queries" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/entities" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/relations" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/summaries" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/graph-view" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/index" in paths
    assert "/workspaces/{workspace_id}/graph-kbs/{graph_id}/jobs/{job_id}" in paths


@pytest.mark.asyncio
async def test_query_graph_passes_resolved_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """query_graph must resolve Chat/Embeddings and attach them to the Worker request."""

    from app.graph_kb.service import query_service as qs

    graph = SimpleNamespace(
        engine=ENGINE_LIGHTRAG,
        indexing_status=STATUS_COMPLETED,
        llm_model_provider="openai",
        llm_model="gpt",
        embedding_model_provider="openai",
        embedding_model="emb",
    )
    llm = SimpleNamespace(endpoint_url="http://llm", api_key="llm-secret", model_name="gpt")
    emb = SimpleNamespace(endpoint_url="http://emb", api_key="emb-secret", model_name="emb")
    captured: dict = {}

    class _Client:
        """Capture the query request sent to the engine client."""

        async def query(self, req):
            captured["req"] = req
            return WorkerQueryResult(answer="ok", citations=[])

    monkeypatch.setattr(qs.graph_svc, "get_graph_for_view", AsyncMock(return_value=graph))
    monkeypatch.setattr(qs, "resolve_graph_models", AsyncMock(return_value=(llm, emb)))
    monkeypatch.setattr(qs, "create_engine_client", lambda: _Client())

    session = AsyncMock()
    session.add = lambda _row: None
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    result = await qs.query_graph(
        session,
        workspace_id=uuid4(),
        graph_id=uuid4(),
        actor=actor,
        query="hello",
        mode="hybrid",
        top_k=5,
    )
    assert result.answer == "ok"
    req = captured["req"]
    assert req.llm is not None
    assert req.embedding is not None
    assert req.llm.api_key == "llm-secret"
    assert req.embedding.model == "emb"
