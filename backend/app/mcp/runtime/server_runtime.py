"""Streamable HTTP runtime for outbound MCP servers (one ASGI handler per slug)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import anyio
from anyio.abc import TaskStatus
from mcp.server.lowlevel.server import Server, request_ctx
from mcp.server.streamable_http import StreamableHTTPServerTransport

from app.core.log import get_logger
from app.mcp.runtime.registry import McpRuntimeRegistry
from app.mcp.runtime.server_exposure import (
    ExposureRuntime,
    call_exposed_tool,
    close_exposure_runtime,
    exposure_runtime_to_mcp_tools,
    open_exposure_runtime,
)
from app.mcp.runtime.snapshots import McpServerSnapshot

log = get_logger(__name__)


def build_mcp_server(snapshot: McpServerSnapshot, registry: McpRuntimeRegistry) -> Server:
    """Build a low-level MCP ``Server`` that exposes the snapshot's tool subset."""

    @asynccontextmanager
    async def lifespan(_server: Server) -> AsyncIterator[ExposureRuntime]:
        runtime = await open_exposure_runtime(snapshot, registry)
        try:
            yield runtime
        finally:
            await close_exposure_runtime(runtime)

    server = Server(f"minerva-mcp-{snapshot.slug}", lifespan=lifespan)

    @server.list_tools()
    async def list_tools() -> list:
        runtime: ExposureRuntime = request_ctx.get().lifespan_context
        return exposure_runtime_to_mcp_tools(runtime)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list:
        runtime: ExposureRuntime = request_ctx.get().lifespan_context
        return await call_exposed_tool(runtime, name, arguments)

    return server


class McpOutboundServerRuntime:
    """Process-wide task group used by stateless Streamable HTTP MCP handlers."""

    def __init__(self) -> None:
        self._task_group: anyio.abc.TaskGroup | None = None

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Start the shared task group for outbound MCP Streamable HTTP requests."""

        async with anyio.create_task_group() as tg:
            self._task_group = tg
            log.info("MCP outbound runtime started", event="mcp.server.runtime.started")
            try:
                yield
            finally:
                self._task_group = None
                log.info("MCP outbound runtime stopped", event="mcp.server.runtime.stopped")

    async def handle_streamable_http(
        self,
        *,
        snapshot: McpServerSnapshot,
        registry: McpRuntimeRegistry,
        scope: dict,
        receive,
        send,
    ) -> None:
        """Serve one Streamable HTTP MCP request for an enabled server snapshot."""

        if self._task_group is None:
            raise RuntimeError("MCP outbound runtime is not started")

        server = build_mcp_server(snapshot, registry)
        transport = StreamableHTTPServerTransport(
            mcp_session_id=None,
            is_json_response_enabled=False,
            event_store=None,
        )

        async def run_stateless_server(*, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
            async with transport.connect() as streams:
                read_stream, write_stream = streams
                task_status.started()
                try:
                    await server.run(
                        read_stream,
                        write_stream,
                        server.create_initialization_options(),
                        stateless=True,
                    )
                except Exception:
                    log.exception(
                        "outbound MCP session crashed slug={}",
                        snapshot.slug,
                        event="mcp.server.session.crashed",
                    )

        await self._task_group.start(run_stateless_server)
        await transport.handle_request(scope, receive, send)
        await transport.terminate()


mcp_outbound_runtime = McpOutboundServerRuntime()
