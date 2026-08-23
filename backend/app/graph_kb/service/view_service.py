"""Build canvas subgraphs from entity/relation projections (BFS, capped)."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.graph_kb.domain.acl import GraphAclActor
from app.graph_kb.domain.db.models import GraphKbEntity, GraphKbRelation
from app.graph_kb.service import graph_service as graph_svc

# Hard cap on nodes returned by graph-view (spec §7.2 / Task 9).
GRAPH_VIEW_MAX_NODES = 200


def _entity_node_id(entity: Any) -> str:
    """Resolve a node id from a dict or ORM-like entity (engine id preferred)."""

    if isinstance(entity, dict):
        return str(entity.get("id") or entity.get("engine_entity_id") or "")
    return str(getattr(entity, "engine_entity_id", None) or getattr(entity, "id", "") or "")


def _relation_ends(relation: Any) -> tuple[str, str]:
    """Return ``(from_id, to_id)`` from a dict or ORM-like relation."""

    if isinstance(relation, dict):
        src = relation.get("from_id") or relation.get("from_entity_id") or ""
        dst = relation.get("to_id") or relation.get("to_entity_id") or ""
        return str(src), str(dst)
    return (
        str(getattr(relation, "from_entity_id", "") or ""),
        str(getattr(relation, "to_entity_id", "") or ""),
    )


def _relation_type(relation: Any) -> str | None:
    """Return relation type label from a dict or ORM-like relation."""

    if isinstance(relation, dict):
        value = relation.get("type") or relation.get("relation_type")
        return str(value) if value is not None else None
    value = getattr(relation, "relation_type", None)
    return str(value) if value is not None else None


def _node_payload(node_id: str, entity: Any | None) -> dict[str, Any]:
    """Serialize one subgraph node for the canvas API."""

    if isinstance(entity, dict):
        return {
            "id": node_id,
            "name": entity.get("name"),
            "entity_type": entity.get("type") or entity.get("entity_type"),
            "description": entity.get("description"),
            "community_id": entity.get("community_id"),
        }
    if entity is not None:
        return {
            "id": node_id,
            "name": getattr(entity, "name", None),
            "entity_type": getattr(entity, "entity_type", None),
            "description": getattr(entity, "description", None),
            "community_id": getattr(entity, "community_id", None),
            "projection_id": getattr(entity, "id", None),
        }
    return {"id": node_id}


def build_subgraph(
    entities: list[Any],
    relations: list[Any],
    *,
    seed_id: str | None,
    hops: int = 1,
    max_nodes: int = GRAPH_VIEW_MAX_NODES,
    community_entity_ids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """BFS subgraph from ``seed_id`` over undirected edges; cap at ``max_nodes``.

    ``entities`` / ``relations`` may be dicts (``id``/``from_id``/``to_id``) or
    projection ORM rows. When ``community_entity_ids`` is set and ``seed_id`` is
    omitted, every community member is treated as a depth-0 seed.
    """

    by_id: dict[str, Any] = {}
    for entity in entities:
        node_id = _entity_node_id(entity)
        if not node_id:
            continue
        if community_entity_ids is not None and node_id not in community_entity_ids:
            continue
        by_id[node_id] = entity

    adjacency: dict[str, set[str]] = defaultdict(set)
    edge_list: list[tuple[str, str, Any]] = []
    for relation in relations:
        src, dst = _relation_ends(relation)
        if not src or not dst:
            continue
        if community_entity_ids is not None and (
            src not in community_entity_ids or dst not in community_entity_ids
        ):
            continue
        adjacency[src].add(dst)
        adjacency[dst].add(src)
        edge_list.append((src, dst, relation))

    for node_id in by_id:
        adjacency.setdefault(node_id, set())

    starts: list[str] = []
    if seed_id:
        starts = [seed_id]
    elif community_entity_ids:
        starts = sorted(nid for nid in community_entity_ids if nid in by_id)
    if not starts:
        return {"nodes": [], "edges": []}

    selected: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque()
    for start in starts:
        if start in selected:
            continue
        if len(selected) >= max_nodes:
            break
        selected[start] = 0
        queue.append((start, 0))

    while queue and len(selected) < max_nodes:
        current, depth = queue.popleft()
        if depth >= hops:
            continue
        for neighbor in adjacency.get(current, ()):
            if neighbor in selected:
                continue
            if len(selected) >= max_nodes:
                break
            selected[neighbor] = depth + 1
            queue.append((neighbor, depth + 1))

    nodes = [_node_payload(node_id, by_id.get(node_id)) for node_id in selected]
    selected_ids = set(selected)
    edges: list[dict[str, Any]] = []
    seen_edge: set[tuple[str, str, str | None]] = set()
    for src, dst, relation in edge_list:
        if src not in selected_ids or dst not in selected_ids:
            continue
        rel_type = _relation_type(relation)
        key = (src, dst, rel_type)
        rev = (dst, src, rel_type)
        if key in seen_edge or rev in seen_edge:
            continue
        seen_edge.add(key)
        if isinstance(relation, dict):
            edges.append(
                {
                    "from_id": src,
                    "to_id": dst,
                    "type": rel_type,
                    "description": relation.get("description"),
                    "weight": relation.get("weight"),
                }
            )
        else:
            edges.append(
                {
                    "from_id": src,
                    "to_id": dst,
                    "type": rel_type,
                    "description": getattr(relation, "description", None),
                    "weight": getattr(relation, "weight", None),
                }
            )

    return {"nodes": nodes, "edges": edges}


async def graph_view(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    actor: GraphAclActor,
    seed_entity_id: str | None = None,
    hops: int = 1,
    community_id: uuid.UUID | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load projections and return a BFS subgraph for the canvas.

    ``seed_entity_id`` may be a projection UUID or an ``engine_entity_id``.
    ``hops`` must be 1 or 2.
    """

    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    if hops not in (1, 2):
        raise AppError("graph_kb.invalid_hops", "hops 仅支持 1 或 2。", 400)
    if not seed_entity_id and community_id is None:
        return {"nodes": [], "edges": []}

    entities = list(
        (
            await session.scalars(
                select(GraphKbEntity).where(
                    GraphKbEntity.workspace_id == workspace_id,
                    GraphKbEntity.graph_id == graph_id,
                )
            )
        ).all()
    )
    relations = list(
        (
            await session.scalars(
                select(GraphKbRelation).where(
                    GraphKbRelation.workspace_id == workspace_id,
                    GraphKbRelation.graph_id == graph_id,
                )
            )
        ).all()
    )

    community_entity_ids: set[str] | None = None
    if community_id is not None:
        community_entity_ids = {
            e.engine_entity_id for e in entities if e.community_id == community_id
        }

    seed_id: str | None = None
    if seed_entity_id:
        raw = seed_entity_id.strip()
        seed_id = raw
        try:
            as_uuid = uuid.UUID(raw)
        except ValueError:
            as_uuid = None
        if as_uuid is not None:
            for entity in entities:
                if entity.id == as_uuid:
                    seed_id = entity.engine_entity_id
                    break

    return build_subgraph(
        entities,
        relations,
        seed_id=seed_id,
        hops=hops,
        max_nodes=GRAPH_VIEW_MAX_NODES,
        community_entity_ids=community_entity_ids,
    )
