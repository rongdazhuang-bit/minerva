"""GraphKB query readiness, subgraph BFS, and related route surface."""

from __future__ import annotations

from app.exceptions import AppError
from app.graph_kb.domain.constants import STATUS_COMPLETED, STATUS_PENDING
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
