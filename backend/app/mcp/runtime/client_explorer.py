"""List and call MCP tools over a short-lived client session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import anyio
from mcp import ClientSession

from app.config import settings
from app.core.log import get_logger
from app.mcp.api.schemas import (
    McpCallToolOut,
    McpListToolsOut,
    McpToolAnnotationOut,
    McpToolOut,
)
from app.mcp.runtime.connection_tester import open_mcp_client_session

log = get_logger(__name__)


@dataclass(frozen=True)
class McpExplorerContext:
    """Transport config passed into one explorer operation."""

    transport: str
    config: dict[str, Any]
    secrets: dict[str, Any]


def map_tool_to_out(tool: Any) -> McpToolOut:
    """Map MCP SDK tool to API output model."""

    annotations = getattr(tool, "annotations", None)
    return McpToolOut(
        name=str(getattr(tool, "name", "") or ""),
        description=getattr(tool, "description", None),
        inputSchema=getattr(tool, "inputSchema", None) or {},
        annotations=McpToolAnnotationOut(
            readOnlyHint=bool(getattr(annotations, "readOnlyHint", False)),
            destructiveHint=bool(getattr(annotations, "destructiveHint", False)),
            idempotentHint=bool(getattr(annotations, "idempotentHint", False)),
            openWorldHint=bool(getattr(annotations, "openWorldHint", False)),
        ),
    )


async def list_tools_on_session(session: ClientSession) -> McpListToolsOut:
    """Call ``list_tools`` on an initialized session."""

    listed = await session.list_tools()
    tools = [map_tool_to_out(tool) for tool in listed.tools if getattr(tool, "name", None)]
    return McpListToolsOut(ok=True, tools=tools)


def serialize_call_tool_result(result: Any) -> McpCallToolOut:
    """Convert MCP ``CallToolResult`` to API output."""

    content_blocks: list[dict[str, Any]] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        block_type = getattr(block, "type", "text")
        if text is not None:
            content_blocks.append({"type": str(block_type), "text": str(text)})
    structured = getattr(result, "structuredContent", None)
    return McpCallToolOut(
        ok=True,
        content=content_blocks,
        structuredContent=structured if isinstance(structured, dict) else None,
        isError=bool(getattr(result, "isError", False)),
    )


async def call_tool_on_session(
    session: ClientSession,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> McpCallToolOut:
    """Call one MCP tool on an initialized session."""

    result = await session.call_tool(tool_name, arguments)
    return serialize_call_tool_result(result)


async def list_tools_for_client(ctx: McpExplorerContext) -> McpListToolsOut:
    """Open session, initialize, list tools, close."""

    timeout = float(settings.mcp_connect_timeout)
    transport_key = (ctx.transport or "").strip().upper()
    try:
        async with asyncio.timeout(timeout):
            async with open_mcp_client_session(
                transport=transport_key,
                config=ctx.config,
                secrets=ctx.secrets,
            ) as session:
                await session.initialize()
                return await list_tools_on_session(session)
    except TimeoutError:
        return McpListToolsOut(
            ok=False,
            tools=[],
            error_code="mcp.client_connect_timeout",
            error_message="MCP connection timed out",
        )
    except anyio.BrokenResourceError as exc:
        return McpListToolsOut(
            ok=False,
            tools=[],
            error_code="mcp.client_stdio_failed",
            error_message=str(exc) or "MCP stdio process failed",
        )
    except Exception as exc:
        log.warn("mcp list_tools failed transport={}", transport_key, exc_info=True)
        code = (
            "mcp.client_stdio_failed"
            if transport_key == "STDIO"
            else "mcp.client_connect_failed"
        )
        return McpListToolsOut(
            ok=False,
            tools=[],
            error_code=code,
            error_message=str(exc) or "MCP connection failed",
        )


async def call_tool_for_client(
    ctx: McpExplorerContext,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> McpCallToolOut:
    """Open session, initialize, call tool, close."""

    timeout = float(settings.mcp_connect_timeout)
    transport_key = (ctx.transport or "").strip().upper()
    try:
        async with asyncio.timeout(timeout):
            async with open_mcp_client_session(
                transport=transport_key,
                config=ctx.config,
                secrets=ctx.secrets,
            ) as session:
                await session.initialize()
                return await call_tool_on_session(
                    session, tool_name=tool_name, arguments=arguments
                )
    except TimeoutError:
        return McpCallToolOut(
            ok=False,
            error_code="mcp.client_connect_timeout",
            error_message="MCP connection timed out",
        )
    except Exception as exc:
        log.warn("mcp call_tool failed tool={}", tool_name, exc_info=True)
        return McpCallToolOut(
            ok=False,
            error_code="mcp.tool_call_failed",
            error_message=str(exc) or "MCP tool call failed",
        )
