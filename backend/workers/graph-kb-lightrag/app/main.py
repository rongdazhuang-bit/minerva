"""FastAPI entrypoint for the isolated LightRAG graph-kb worker."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth import api_key_middleware
from app.store import build_store

app = FastAPI(title="Minerva GraphKB LightRAG Worker", version="0.1.0")
app.middleware("http")(api_key_middleware)
# Shared store for the process lifetime (fake or real based on env at import).
_store = build_store()


class DocumentIn(BaseModel):
    """One document payload for ``/index``."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    name: str = ""
    text: str = ""


class NamespaceBody(BaseModel):
    """Common body: only ``workspace_id`` + ``graph_id`` define the silo.

    Extra keys such as ``workspace`` / ``lightrag_workspace`` are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    workspace_id: UUID
    graph_id: UUID
    engine: str = "lightrag"


class IndexBody(NamespaceBody):
    """Index request matching ``HttpGraphEngineClient.index`` JSON."""

    documents: list[DocumentIn] = Field(default_factory=list)


class QueryBody(NamespaceBody):
    """Query request matching ``HttpGraphEngineClient.query`` JSON."""

    query: str
    mode: str = "hybrid"
    top_k: int = 10


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for local scripts and ops checks."""

    return {"status": "ok"}


@app.post("/index")
async def index(body: IndexBody) -> dict[str, Any]:
    """Index documents and return entity/relation export."""

    documents = [
        {
            "document_id": d.document_id,
            "name": d.name,
            "text": d.text,
        }
        for d in body.documents
    ]
    return await _store.index(
        workspace_id=body.workspace_id,
        graph_id=body.graph_id,
        documents=documents,
    )


@app.post("/query")
async def query(body: QueryBody) -> dict[str, Any]:
    """Run a retrieval/QA query against the LightRAG (or fake) store."""

    return await _store.query(
        workspace_id=body.workspace_id,
        graph_id=body.graph_id,
        query=body.query,
        mode=body.mode,
        top_k=body.top_k,
    )


@app.post("/export_graph")
async def export_graph(body: NamespaceBody) -> dict[str, Any]:
    """Export entities and relations for projection tables/canvas."""

    return await _store.export_graph(
        workspace_id=body.workspace_id, graph_id=body.graph_id
    )


@app.post("/list_summaries")
async def list_summaries(body: NamespaceBody) -> dict[str, Any]:
    """List topic/community summaries; wrap as ``{"summaries": [...]}``."""

    rows = await _store.list_summaries(
        workspace_id=body.workspace_id, graph_id=body.graph_id
    )
    return {"summaries": rows}


@app.post("/delete_namespace")
async def delete_namespace(body: NamespaceBody) -> Response:
    """Clear worker storage for the given workspace+graph pair."""

    await _store.delete_namespace(
        workspace_id=body.workspace_id, graph_id=body.graph_id
    )
    return Response(status_code=204)
