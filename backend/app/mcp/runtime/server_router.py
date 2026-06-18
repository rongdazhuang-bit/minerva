"""Mount outbound MCP server routes from registry snapshots."""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.log import get_logger
from app.mcp.runtime.snapshots import McpServerSnapshot
from app.mcp.runtime.registry import McpRuntimeRegistry

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
    """Register lightweight MCP server health routes for enabled snapshots."""

    global _MOUNTED
    if not settings.mcp_server_enabled:
        return

    @app.get("/mcp/s/{slug}/health")
    async def mcp_server_health(
        slug: str,
        request: Request,
        authorization: str | None = Header(default=None),  # noqa: ARG001
    ) -> JSONResponse:
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
            }
        )

    _MOUNTED = True
    log.info("MCP server routes mounted", event="mcp.server.routes.mounted")
