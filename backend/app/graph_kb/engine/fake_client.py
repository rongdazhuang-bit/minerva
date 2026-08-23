"""In-process Fake GraphEngineClient keyed by (workspace_id, graph_id)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.graph_kb.engine.types import (
    GraphExport,
    SummaryItem,
    WorkerIndexRequest,
    WorkerQueryRequest,
    WorkerQueryResult,
)


@dataclass
class _FakeStore:
    """Per-namespace fake index state for isolation tests and local runs."""

    # Joined document texts used to build query answers (e.g. ``fake:alpha``).
    texts: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    summaries: list[SummaryItem] = field(default_factory=list)


class FakeGraphEngineClient:
    """Process-local fake worker; store key MUST be ``(workspace_id, graph_id)``."""

    def __init__(self) -> None:
        """Initialize an empty in-memory namespace store."""

        # Isolation key: never collapse to a single workspace string.
        self._store: dict[tuple[UUID, UUID], _FakeStore] = {}

    def _ns(self, workspace_id: UUID, graph_id: UUID) -> _FakeStore:
        """Return (creating if needed) the store for one workspace+graph pair."""

        key = (workspace_id, graph_id)
        if key not in self._store:
            self._store[key] = _FakeStore()
        return self._store[key]

    async def index(self, req: WorkerIndexRequest) -> GraphExport:
        """Index docs into one entity + one relation + one summary for projection tests."""

        ns = self._ns(req.workspace_id, req.graph_id)
        texts = [d.text for d in req.documents]
        joined = "\n".join(texts)
        entity_id = f"ent-{req.graph_id.hex[:8]}"
        entity = {
            "id": entity_id,
            "name": joined or (req.documents[0].name if req.documents else "empty"),
            "type": "document",
            "description": joined,
        }
        relation = {
            "id": f"rel-{req.graph_id.hex[:8]}",
            "from_id": entity_id,
            "to_id": entity_id,
            "type": "self",
            "description": "fake index relation",
        }
        summary = SummaryItem(
            summary_id=f"sum-{req.graph_id.hex[:8]}",
            title=f"Summary {req.graph_id.hex[:8]}",
            content=joined,
            level=0,
            parent_id=None,
        )
        ns.texts = texts
        ns.entities = [entity]
        ns.relations = [relation]
        ns.summaries = [summary]
        return GraphExport(entities=list(ns.entities), relations=list(ns.relations))

    async def query(self, req: WorkerQueryRequest) -> WorkerQueryResult:
        """Return ``fake:`` plus indexed document text for the target graph."""

        ns = self._ns(req.workspace_id, req.graph_id)
        joined = "\n".join(ns.texts) if ns.texts else req.query
        return WorkerQueryResult(answer=f"fake:{joined}", citations=[])

    async def export_graph(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> GraphExport:
        """Return entities/relations stored for this namespace (empty if never indexed)."""

        ns = self._ns(workspace_id, graph_id)
        return GraphExport(entities=list(ns.entities), relations=list(ns.relations))

    async def list_summaries(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> list[SummaryItem]:
        """Return fake summaries for this namespace."""

        return list(self._ns(workspace_id, graph_id).summaries)

    async def delete_namespace(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> None:
        """Drop the in-memory store for this workspace+graph pair."""

        self._store.pop((workspace_id, graph_id), None)
