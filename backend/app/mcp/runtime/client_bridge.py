"""Bridge MCP client sessions to LangChain tools for Agent runs."""

from __future__ import annotations

import json
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession

from app.core.log import get_logger
from app.mcp.runtime.connection_tester import McpConnectionTester
from app.mcp.runtime.snapshots import McpClientSnapshot

log = get_logger(__name__)


@dataclass
class OpenMcpClientBundle:
    """One live MCP client session plus metadata for cleanup after an Agent run."""

    snapshot: McpClientSnapshot
    session: ClientSession
    stack: AsyncExitStack


def mcp_tool_name(client_name: str, original: str) -> str:
    """Build a LangChain-safe tool name that avoids collisions with built-in skills."""

    safe = re.sub(r"[^a-z0-9]+", "_", client_name.lower()).strip("_") or "client"
    return f"mcp__{safe}__{original}"


async def open_mcp_client_bundle(snapshot: McpClientSnapshot) -> OpenMcpClientBundle | None:
    """Open one MCP client session for an enabled snapshot."""

    stack = AsyncExitStack()
    try:
        tester = McpConnectionTester()
        session = await stack.enter_async_context(
            tester._open_session(
                transport=snapshot.transport,
                config=snapshot.config,
                secrets=snapshot.secrets,
            )
        )
        await session.initialize()
        return OpenMcpClientBundle(snapshot=snapshot, session=session, stack=stack)
    except Exception:
        log.exception("failed to open MCP client name={}", snapshot.name)
        await stack.aclose()
        return None


async def build_langchain_tools_from_bundle(
    bundle: OpenMcpClientBundle,
) -> list[StructuredTool]:
    """Convert MCP tools from one open session into LangChain ``StructuredTool`` list."""

    listed = await bundle.session.list_tools()
    tools: list[StructuredTool] = []
    for mcp_tool in listed.tools:
        original = getattr(mcp_tool, "name", None)
        if not isinstance(original, str) or not original.strip():
            continue
        lc_name = mcp_tool_name(bundle.snapshot.name, original)
        description = getattr(mcp_tool, "description", None) or f"MCP tool {original}"

        async def _call_tool(
            payload: str = "{}",
            *,
            _session: ClientSession = bundle.session,
            _tool_name: str = original,
        ) -> str:
            try:
                args = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                args = {"input": payload}
            if not isinstance(args, dict):
                args = {"input": args}
            result = await _session.call_tool(_tool_name, args)
            if getattr(result, "structuredContent", None) is not None:
                return json.dumps(result.structuredContent, ensure_ascii=False)
            chunks = []
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(str(text))
            return "\n".join(chunks) if chunks else str(result)

        tools.append(
            StructuredTool.from_function(
                coroutine=_call_tool,
                name=lc_name,
                description=description,
            )
        )
    return tools


async def load_langchain_tools_for_snapshots(
    snapshots: list[McpClientSnapshot],
) -> tuple[list[StructuredTool], list[OpenMcpClientBundle]]:
    """Open all snapshots and aggregate LangChain tools (failures are skipped)."""

    all_tools: list[StructuredTool] = []
    bundles: list[OpenMcpClientBundle] = []
    seen_names: set[str] = set()
    for snapshot in snapshots:
        if not snapshot.enabled:
            continue
        bundle = await open_mcp_client_bundle(snapshot)
        if bundle is None:
            continue
        bundles.append(bundle)
        for tool in await build_langchain_tools_from_bundle(bundle):
            if tool.name in seen_names:
                continue
            seen_names.add(tool.name)
            all_tools.append(tool)
    return all_tools, bundles


async def close_mcp_client_bundles(bundles: list[OpenMcpClientBundle]) -> None:
    """Close all MCP client sessions opened for one Agent run."""

    for bundle in bundles:
        try:
            await bundle.stack.aclose()
        except Exception:
            log.exception("failed to close MCP client name={}", bundle.snapshot.name)
