"""Aggregate builtin skill tools and MCP client tools for outbound MCP servers."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import mcp.types as types
from langchain_core.tools import BaseTool
from mcp import ClientSession

from app.agent.infrastructure.skill_loader import list_indexed_skill_ids, load_tools_for_skill
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.core.log import get_logger
from app.mcp.runtime.client_bridge import (
    OpenMcpClientBundle,
    close_mcp_client_bundles,
    mcp_tool_name,
    open_mcp_client_bundle,
)
from app.mcp.runtime.tool_result_text import format_mcp_call_tool_result
from app.mcp.runtime.registry import McpRuntimeRegistry
from app.mcp.runtime.snapshots import McpClientSnapshot, McpServerSnapshot

log = get_logger(__name__)


@dataclass
class ExposedToolEntry:
    """One tool exposed on the outbound MCP server with routing metadata."""

    mcp_name: str
    description: str
    input_schema: dict[str, Any]
    source_kind: str
    skill_id: str | None = None
    lc_tool: BaseTool | None = None
    client_session: ClientSession | None = None
    client_tool_name: str | None = None


@dataclass
class ExposureRuntime:
    """Live resources opened for one outbound MCP session."""

    tools: list[ExposedToolEntry] = field(default_factory=list)
    tools_by_name: dict[str, ExposedToolEntry] = field(default_factory=dict)
    bundles: list[OpenMcpClientBundle] = field(default_factory=list)


def skill_tool_name(skill_id: str, original: str) -> str:
    """Build a stable MCP tool name for one builtin skill tool."""

    safe_skill = re.sub(r"[^a-z0-9]+", "_", skill_id.lower()).strip("_") or "skill"
    safe_tool = re.sub(r"[^a-z0-9]+", "_", original.lower()).strip("_") or "tool"
    return f"skill__{safe_skill}__{safe_tool}"


def resolve_exposure_skill_ids(exposure: dict[str, Any]) -> list[str]:
    """Return builtin skill ids included by an exposure JSON payload."""

    if exposure.get("include_all_builtin"):
        return list_indexed_skill_ids()
    raw = exposure.get("builtin_skills")
    if not isinstance(raw, list):
        return []
    allowed = set(list_indexed_skill_ids())
    return [str(item).strip().lower() for item in raw if str(item).strip().lower() in allowed]


def resolve_exposure_client_snapshots(
    exposure: dict[str, Any],
    *,
    workspace_id: uuid.UUID,
    registry: McpRuntimeRegistry,
) -> list[McpClientSnapshot]:
    """Return MCP client snapshots referenced by an exposure JSON payload."""

    all_clients = registry.list_client_snapshots(workspace_id)
    if exposure.get("include_all_clients"):
        return [client for client in all_clients if client.enabled]
    raw_ids = exposure.get("mcp_client_ids")
    if not isinstance(raw_ids, list):
        return []
    wanted = {str(item) for item in raw_ids}
    return [client for client in all_clients if str(client.id) in wanted and client.enabled]


def _langchain_tool_input_schema(tool: BaseTool) -> dict[str, Any]:
    """Convert a LangChain tool args schema to JSON Schema for MCP ``inputSchema``."""

    schema = getattr(tool, "args_schema", None)
    if schema is not None and hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    return {"type": "object", "properties": {}}


async def _collect_builtin_tools(
    snapshot: McpServerSnapshot,
    skill_ids: list[str],
) -> list[ExposedToolEntry]:
    """Load builtin skill tools for the configured exposure subset."""

    ctx = SkillToolContext(workspace_id=snapshot.workspace_id, chat_model=None)
    entries: list[ExposedToolEntry] = []
    seen: set[str] = set()
    for skill_id in skill_ids:
        for lc_tool in load_tools_for_skill(skill_id, ctx):
            original = getattr(lc_tool, "name", None)
            if not isinstance(original, str) or not original.strip():
                continue
            mcp_name = skill_tool_name(skill_id, original)
            if mcp_name in seen:
                continue
            seen.add(mcp_name)
            entries.append(
                ExposedToolEntry(
                    mcp_name=mcp_name,
                    description=getattr(lc_tool, "description", None) or f"Skill {skill_id} tool {original}",
                    input_schema=_langchain_tool_input_schema(lc_tool),
                    source_kind="builtin",
                    skill_id=skill_id,
                    lc_tool=lc_tool,
                )
            )
    return entries


async def _collect_client_tools(
    client_snapshots: list[McpClientSnapshot],
) -> tuple[list[ExposedToolEntry], list[OpenMcpClientBundle]]:
    """Open MCP clients and map their tools into outbound exposure entries."""

    entries: list[ExposedToolEntry] = []
    bundles: list[OpenMcpClientBundle] = []
    seen: set[str] = set()
    for snapshot in client_snapshots:
        bundle = await open_mcp_client_bundle(snapshot)
        if bundle is None:
            log.warning(
                "failed to open MCP client for outbound exposure name={}",
                snapshot.name,
            )
            continue
        bundles.append(bundle)
        listed = await bundle.session.list_tools()
        for mcp_tool in listed.tools:
            original = getattr(mcp_tool, "name", None)
            if not isinstance(original, str) or not original.strip():
                continue
            exposed_name = mcp_tool_name(snapshot.name, original)
            if exposed_name in seen:
                continue
            seen.add(exposed_name)
            schema = getattr(mcp_tool, "input_schema", None)
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            entries.append(
                ExposedToolEntry(
                    mcp_name=exposed_name,
                    description=getattr(mcp_tool, "description", None) or f"MCP tool {original}",
                    input_schema=schema,
                    source_kind="client",
                    client_session=bundle.session,
                    client_tool_name=original,
                )
            )
    return entries, bundles


async def open_exposure_runtime(
    snapshot: McpServerSnapshot,
    registry: McpRuntimeRegistry,
) -> ExposureRuntime:
    """Open all resources required to serve one outbound MCP exposure config."""

    exposure = dict(snapshot.exposure or {})
    skill_ids = resolve_exposure_skill_ids(exposure)
    client_snapshots = resolve_exposure_client_snapshots(
        exposure,
        workspace_id=snapshot.workspace_id,
        registry=registry,
    )
    runtime = ExposureRuntime()
    runtime.tools.extend(await _collect_builtin_tools(snapshot, skill_ids))
    client_entries, bundles = await _collect_client_tools(client_snapshots)
    runtime.tools.extend(client_entries)
    runtime.bundles = bundles
    runtime.tools_by_name = {entry.mcp_name: entry for entry in runtime.tools}
    return runtime


async def close_exposure_runtime(runtime: ExposureRuntime) -> None:
    """Close MCP client sessions opened for one outbound exposure runtime."""

    await close_mcp_client_bundles(runtime.bundles)


def exposure_runtime_to_mcp_tools(runtime: ExposureRuntime) -> list[types.Tool]:
    """Convert collected exposure entries to MCP ``Tool`` descriptors."""

    return [
        types.Tool(
            name=entry.mcp_name,
            description=entry.description,
            input_schema=entry.input_schema,
        )
        for entry in runtime.tools
    ]


async def call_exposed_tool(runtime: ExposureRuntime, name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Execute one exposed tool and normalize the response to MCP text content."""

    entry = runtime.tools_by_name.get(name)
    if entry is None:
        raise ValueError(f"Unknown tool: {name}")
    args = arguments or {}
    if entry.source_kind == "builtin" and entry.lc_tool is not None:
        if hasattr(entry.lc_tool, "ainvoke"):
            result = await entry.lc_tool.ainvoke(args)
        else:
            result = entry.lc_tool.invoke(args)
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, ensure_ascii=False, default=str)
        return [types.TextContent(type="text", text=text)]
    if entry.source_kind == "client" and entry.client_session is not None and entry.client_tool_name:
        result = await entry.client_session.call_tool(entry.client_tool_name, args)
        text = format_mcp_call_tool_result(result)
        return [types.TextContent(type="text", text=text)]
    raise ValueError(f"Tool {name} is not callable")
