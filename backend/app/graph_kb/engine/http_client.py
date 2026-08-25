"""HTTP GraphEngineClient posting workspace_id/graph_id JSON to engine workers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.exceptions import AppError
from app.graph_kb.domain.constants import ENGINE_GRAPHRAG, ENGINE_LIGHTRAG
from app.graph_kb.engine.types import (
    GraphExport,
    ModelEndpoint,
    SummaryItem,
    WorkerIndexRequest,
    WorkerQueryRequest,
    WorkerQueryResult,
)


def _endpoint_dict(ep: ModelEndpoint) -> dict[str, str]:
    """Serialize a model endpoint for worker JSON."""

    return {"base_url": ep.base_url, "api_key": ep.api_key, "model": ep.model}


def _auth_headers(engine: str) -> dict[str, str]:
    """Build Authorization header for the given engine worker."""

    if engine == ENGINE_LIGHTRAG:
        key = settings.graph_kb_lightrag_worker_api_key.strip()
    elif engine == ENGINE_GRAPHRAG:
        key = settings.graph_kb_graphrag_worker_api_key.strip()
    else:
        raise AppError("graph_kb.invalid_engine", f"未知引擎: {engine}", 400)
    return {"Authorization": f"Bearer {key}"}


class HttpGraphEngineClient:
    """Call LightRAG / GraphRAG workers over HTTP; never send pre-built namespaces."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Optionally inject an httpx transport (tests use ``MockTransport``)."""

        self._transport = transport

    def _base_url(self, engine: str) -> str:
        """Resolve worker base URL from settings for the given engine id."""

        if engine == ENGINE_LIGHTRAG:
            return settings.graph_kb_lightrag_worker_url.rstrip("/")
        if engine == ENGINE_GRAPHRAG:
            return settings.graph_kb_graphrag_worker_url.rstrip("/")
        raise AppError("graph_kb.invalid_engine", f"未知引擎: {engine}", 400)

    async def _post(self, engine: str, action: str, payload: dict[str, Any]) -> Any:
        """POST JSON to ``{worker}/{action}``; map connection failures to 503."""

        # Hard invariant: callers must not smuggle pre-built workspace strings.
        if "lightrag_workspace" in payload or "workspace" in payload:
            raise AppError(
                "graph_kb.invalid_worker_payload",
                "主 API 不得向 Worker 发送预拼 workspace 字符串。",
                500,
            )
        url = f"{self._base_url(engine)}/{action.lstrip('/')}"
        timeout = settings.graph_kb_job_timeout_seconds
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self._transport
            ) as client:
                response = await client.post(url, json=payload, headers=_auth_headers(engine))
                response.raise_for_status()
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()
        except httpx.RequestError as exc:
            raise AppError(
                "graph_kb.worker_unavailable",
                "图谱引擎 Worker 不可用。",
                503,
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise AppError(
                    "graph_kb.worker_unauthorized",
                    "图谱引擎 Worker 认证失败。",
                    502,
                ) from exc
            raise AppError(
                "graph_kb.worker_error",
                f"图谱引擎 Worker 返回错误: HTTP {exc.response.status_code}",
                502,
            ) from exc

    async def index(self, req: WorkerIndexRequest) -> GraphExport:
        """POST ``/index`` with UUID fields and document/model payloads."""

        payload = {
            "workspace_id": str(req.workspace_id),
            "graph_id": str(req.graph_id),
            "engine": req.engine,
            "documents": [
                {
                    "document_id": str(d.document_id),
                    "name": d.name,
                    "text": d.text,
                }
                for d in req.documents
            ],
            "llm": _endpoint_dict(req.llm),
            "embedding": _endpoint_dict(req.embedding),
        }
        data = await self._post(req.engine, "index", payload)
        return GraphExport(
            entities=list(data.get("entities") or []),
            relations=list(data.get("relations") or []),
        )

    async def query(self, req: WorkerQueryRequest) -> WorkerQueryResult:
        """POST ``/query`` with workspace_id, graph_id, mode, top_k, and models."""

        payload = {
            "workspace_id": str(req.workspace_id),
            "graph_id": str(req.graph_id),
            "engine": req.engine,
            "query": req.query,
            "mode": req.mode,
            "top_k": req.top_k,
        }
        if req.llm is not None:
            payload["llm"] = _endpoint_dict(req.llm)
        if req.embedding is not None:
            payload["embedding"] = _endpoint_dict(req.embedding)
        data = await self._post(req.engine, "query", payload)
        return WorkerQueryResult(
            answer=str(data.get("answer") or ""),
            citations=list(data.get("citations") or []),
        )

    async def export_graph(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> GraphExport:
        """POST ``/export_graph`` for the given namespace UUIDs."""

        payload = {
            "workspace_id": str(workspace_id),
            "graph_id": str(graph_id),
            "engine": engine,
        }
        data = await self._post(engine, "export_graph", payload)
        return GraphExport(
            entities=list(data.get("entities") or []),
            relations=list(data.get("relations") or []),
        )

    async def list_summaries(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> list[SummaryItem]:
        """POST ``/list_summaries`` and map rows to ``SummaryItem``."""

        payload = {
            "workspace_id": str(workspace_id),
            "graph_id": str(graph_id),
            "engine": engine,
        }
        data = await self._post(engine, "list_summaries", payload)
        rows = data if isinstance(data, list) else list(data.get("summaries") or [])
        return [
            SummaryItem(
                summary_id=str(row["summary_id"]),
                title=str(row.get("title") or ""),
                content=str(row.get("content") or ""),
                level=int(row.get("level") or 0),
                parent_id=row.get("parent_id"),
            )
            for row in rows
        ]

    async def delete_namespace(
        self, *, engine: str, workspace_id: UUID, graph_id: UUID
    ) -> None:
        """POST ``/delete_namespace`` to clear worker storage for this pair."""

        payload = {
            "workspace_id": str(workspace_id),
            "graph_id": str(graph_id),
            "engine": engine,
        }
        await self._post(engine, "delete_namespace", payload)
