"""Protocol for GraphKB engine workers (index / query / export / summaries / delete)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.graph_kb.engine.types import (
    GraphExport,
    SummaryItem,
    WorkerIndexRequest,
    WorkerQueryRequest,
    WorkerQueryResult,
)


class GraphEngineClient(Protocol):
    """Async client contract for LightRAG / GraphRAG workers.

    Implementations must send ``workspace_id`` and ``graph_id`` only — never a
    pre-built LightRAG workspace string or GraphRAG root path.
    """

    async def index(self, req: WorkerIndexRequest) -> GraphExport:
        """Index documents and return an entity/relation export snapshot."""

    async def query(self, req: WorkerQueryRequest) -> WorkerQueryResult:
        """Run a retrieval/QA query against the indexed namespace."""

    async def export_graph(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> GraphExport:
        """Fetch the current entity/relation graph from the worker."""

    async def list_summaries(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> list[SummaryItem]:
        """List community / topic summaries for projection."""

    async def delete_namespace(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> None:
        """Delete all engine data for the given workspace + graph pair."""
