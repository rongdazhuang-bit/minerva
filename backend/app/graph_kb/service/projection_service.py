"""Replace GraphKB read-only entity / relation / community projections."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_kb.domain.db.models import GraphKbCommunity, GraphKbEntity, GraphKbRelation
from app.graph_kb.engine.types import GraphExport, SummaryItem


def summaries_to_rows(
    summaries: list[SummaryItem],
    *,
    graph_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Map worker ``SummaryItem`` values to community projection dicts (no DB)."""

    rows: list[dict[str, Any]] = []
    for item in summaries:
        rows.append(
            {
                "engine_community_id": item.summary_id,
                "title": item.title,
                "summary": item.content,
                "level": item.level,
                "parent_id": item.parent_id,
                "graph_id": graph_id,
                "workspace_id": workspace_id,
            }
        )
    return rows


def entities_to_rows(
    entities: list[dict[str, Any]],
    *,
    graph_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Map worker entity dicts onto ``graph_kb_entity`` column names."""

    rows: list[dict[str, Any]] = []
    for entity in entities:
        engine_id = entity.get("id") or entity.get("engine_entity_id") or ""
        rows.append(
            {
                "engine_entity_id": str(engine_id),
                "name": str(entity.get("name") or "")[:512],
                "entity_type": entity.get("type") or entity.get("entity_type"),
                "description": entity.get("description"),
                "community_id": entity.get("community_id"),
                "graph_id": graph_id,
                "workspace_id": workspace_id,
            }
        )
    return rows


def relations_to_rows(
    relations: list[dict[str, Any]],
    *,
    graph_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Map worker relation dicts onto ``graph_kb_relation`` column names."""

    rows: list[dict[str, Any]] = []
    for relation in relations:
        rows.append(
            {
                "from_entity_id": str(
                    relation.get("from_id") or relation.get("from_entity_id") or ""
                ),
                "to_entity_id": str(relation.get("to_id") or relation.get("to_entity_id") or ""),
                "relation_type": relation.get("type") or relation.get("relation_type"),
                "description": relation.get("description"),
                "weight": relation.get("weight"),
                "graph_id": graph_id,
                "workspace_id": workspace_id,
            }
        )
    return rows


def _as_uuid(value: Any) -> uuid.UUID | None:
    """Parse a UUID string; return None when missing or invalid."""

    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def replace_projections(
    session: AsyncSession,
    *,
    graph_id: uuid.UUID,
    workspace_id: uuid.UUID,
    export: GraphExport,
    summaries: list[SummaryItem],
) -> None:
    """Delete this graph's three projection tables, then insert export + summaries.

    Call only after a successful Worker index. Failed jobs must skip this function
    so the previous snapshot remains.
    """

    for model in (GraphKbCommunity, GraphKbRelation, GraphKbEntity):
        await session.execute(
            delete(model).where(
                model.workspace_id == workspace_id,
                model.graph_id == graph_id,
            )
        )

    community_ids: dict[str, uuid.UUID] = {}
    pending_parents: list[tuple[GraphKbCommunity, str]] = []
    for row in summaries_to_rows(summaries, graph_id=graph_id, workspace_id=workspace_id):
        community_pk = uuid.uuid4()
        engine_id = str(row["engine_community_id"])
        community_ids[engine_id] = community_pk
        community = GraphKbCommunity(
            id=community_pk,
            workspace_id=workspace_id,
            graph_id=graph_id,
            engine_community_id=engine_id,
            title=row["title"],
            summary=row["summary"],
            level=row["level"],
            parent_id=None,
        )
        parent_raw = row.get("parent_id")
        if parent_raw:
            pending_parents.append((community, str(parent_raw)))
        session.add(community)

    for community, parent_engine_id in pending_parents:
        mapped = community_ids.get(parent_engine_id) or _as_uuid(parent_engine_id)
        community.parent_id = mapped

    for row in entities_to_rows(export.entities, graph_id=graph_id, workspace_id=workspace_id):
        community_ref = row.get("community_id")
        community_pk = None
        if community_ref is not None:
            community_pk = community_ids.get(str(community_ref)) or _as_uuid(community_ref)
        session.add(
            GraphKbEntity(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                engine_entity_id=row["engine_entity_id"],
                name=row["name"],
                entity_type=row["entity_type"],
                description=row["description"],
                community_id=community_pk,
            )
        )

    for row in relations_to_rows(export.relations, graph_id=graph_id, workspace_id=workspace_id):
        session.add(
            GraphKbRelation(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                from_entity_id=row["from_entity_id"],
                to_entity_id=row["to_entity_id"],
                relation_type=row["relation_type"],
                description=row["description"],
                weight=row["weight"],
            )
        )
    await session.flush()
