"""Shared request/response dataclasses for GraphKB engine worker calls."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class WorkerDocument:
    """One document payload for worker ``index``."""

    document_id: UUID
    name: str
    text: str


@dataclass(frozen=True)
class WorkerIndexRequest:
    """Index request: UUIDs only — workers build their own namespaces."""

    workspace_id: UUID
    graph_id: UUID
    engine: str
    documents: list[WorkerDocument]


@dataclass(frozen=True)
class GraphExport:
    """Entity/relation snapshot returned by worker index or export."""

    entities: list[dict]
    relations: list[dict]


@dataclass(frozen=True)
class SummaryItem:
    """Community / topic summary row for projection."""

    summary_id: str
    title: str
    content: str
    level: int
    parent_id: str | None


@dataclass(frozen=True)
class WorkerQueryRequest:
    """Query request scoped by workspace + graph UUIDs."""

    workspace_id: UUID
    graph_id: UUID
    engine: str
    query: str
    mode: str
    top_k: int


@dataclass(frozen=True)
class WorkerQueryResult:
    """Answer and optional citation dicts from worker ``query``."""

    answer: str
    citations: list[dict]
