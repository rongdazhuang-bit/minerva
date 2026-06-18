"""Mount outbound MCP server routes from registry snapshots."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app.config import settings
from app.core.log import get_logger
from app.mcp.runtime.registry import McpRuntimeRegistry
from app.mcp.runtime.server_runtime import mcp_outbound_runtime
from app.mcp.runtime.snapshots import McpServerSnapshot

log = get_logger(__name__)

_MOUNTED = False


def _find_snapshot(registry: McpRuntimeRegistry, slug: str) -> McpServerSnapshot | None:
    for snap in registry.list_server_snapshots():
        if snap.slug == slug and snap.enabled:
            return snap
    return None


def _authorize(snapshot: McpServerSnapshot, request: Request) -> None:
    if snapshot.auth_type == "NONE":
        return
    if snapshot.auth_type == "BEARER":
        auth = request.headers.get("Authorization") or ""
        token = auth.removeprefix("Bearer").strip()
        if not snapshot.auth_secret or token != snapshot.auth_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return
    if snapshot.auth_type == "API_KEY":
        key = request.headers.get("X-API-Key") or ""
        if not snapshot.auth_secret or key != snapshot.auth_secret:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def mount_mcp_server_routes(app: FastAPI, registry: McpRuntimeRegistry) -> None:
    """Register outbound MCP Streamable HTTP routes for enabled server snapshots."""

    global _MOUNTED
    if not settings.mcp_server_enabled:
        return
    if _MOUNTED:
        return

    @app.get("/mcp/s/{slug}/health")
    async def mcp_server_health(slug: str, request: Request) -> JSONResponse:
        snapshot = _find_snapshot(registry, slug.strip().lower())
        if snapshot is None:
            raise HTTPException(status_code=404, detail="MCP server not found")
        _authorize(snapshot, request)
        return JSONResponse(
            {
                "slug": snapshot.slug,
                "workspace_id": str(snapshot.workspace_id),
                "exposure": snapshot.exposure,
                "status": "ok",
                "transport": "streamable-http",
            }
        )

    async def _streamable_http_asgi(scope: Scope, receive: Receive, send: Send) -> None:
        slug = str(scope.get("path_params", {}).get("slug", "")).strip().lower()
        snapshot = _find_snapshot(registry, slug)
        if snapshot is None:
            response = JSONResponse(status_code=404, content={"detail": "MCP server not found"})
            await response(scope, receive, send)
            return
        request = Request(scope, receive)
        try:
            _authorize(snapshot, request)
        except HTTPException as exc:
            response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            await response(scope, receive, send)
            return
        await mcp_outbound_runtime.handle_streamable_http(
            snapshot=snapshot,
            registry=registry,
            scope=scope,
            receive=receive,
            send=send,
        )

    app.add_api_route(
        "/mcp/s/{slug}",
        _streamable_http_asgi,
        methods=["GET", "POST", "DELETE"],
        name="mcp_server_streamable_http",
    )

    _MOUNTED = True
    log.info("MCP server routes mounted", event="mcp.server.routes.mounted")
