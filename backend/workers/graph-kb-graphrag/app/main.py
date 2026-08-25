"""FastAPI entrypoint for the isolated GraphRAG graph-kb worker."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth import api_key_middleware
from app.store import build_store

app = FastAPI(title="Minerva GraphKB GraphRAG Worker", version="0.1.0")
app.middleware("http")(api_key_middleware)
# Shared store for the process lifetime (fake or real based on env at import).
_store = build_store()


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map forbidden ``root`` field to HTTP 400; keep other validation as 422."""

    _ = request
    errors = exc.errors()
    for err in errors:
        msg = str(err.get("msg") or "")
        if "root" in msg.lower():
            return JSONResponse(status_code=400, content={"detail": msg})
    return JSONResponse(status_code=422, content={"detail": errors})


class DocumentIn(BaseModel):
    """One document payload for ``/index``."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    name: str = ""
    text: str = ""


class NamespaceBody(BaseModel):
    """Common body: only ``workspace_id`` + ``graph_id`` define the silo.

    A client-supplied ``root`` field is rejected (HTTP 400). Other unknown
    keys such as ``workspace`` are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    workspace_id: UUID
    graph_id: UUID
    engine: str = "graphrag"

    @model_validator(mode="before")
    @classmethod
    def reject_client_root(cls, data: Any) -> Any:
        """Forbid request field ``root``; silo path comes only from UUIDs + env."""

        if isinstance(data, dict) and "root" in data:
            raise ValueError(
                "Request field 'root' is not allowed; use workspace_id and graph_id only."
            )
        return data


class IndexBody(NamespaceBody):
    """Index request matching ``HttpGraphEngineClient.index`` JSON."""

    documents: list[DocumentIn] = Field(default_factory=list)
    # Optional override for ``graphrag index`` subprocess timeout (seconds).
    timeout_seconds: int | None = None


class QueryBody(NamespaceBody):
    """Query request matching ``HttpGraphEngineClient.query`` JSON."""

    query: str
    mode: str = "global"
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
        timeout_seconds=body.timeout_seconds,
    )


@app.post("/query")
async def query(body: QueryBody) -> dict[str, Any]:
    """Run a retrieval/QA query against the GraphRAG (or fake) store."""

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
    """List community summaries; wrap as ``{"summaries": [...]}``."""

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
