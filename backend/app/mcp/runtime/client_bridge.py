"""Bridge MCP client sessions to LangChain tools for Agent runs."""

from __future__ import annotations

import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from pydantic import BaseModel, ConfigDict, Field, create_model

from app.core.log import get_logger
from app.mcp.runtime.connection_tester import open_mcp_client_session
from app.mcp.runtime.snapshots import McpClientSnapshot
from app.mcp.runtime.tool_result_text import format_mcp_call_tool_result

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


def _safe_model_suffix(name: str) -> str:
    """Sanitize an MCP tool name for use in a dynamic Pydantic model class name."""

    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_")
    if not safe or safe[0].isdigit():
        safe = f"T_{safe or 'tool'}"
    return safe[:64]


def _json_schema_property_type(prop: dict[str, Any]) -> tuple[type[Any], bool]:
    """Map one JSON Schema property to a Python type and whether ``null`` is allowed."""

    raw_type = prop.get("type", "string")
    nullable = False
    if isinstance(raw_type, list):
        nullable = "null" in raw_type
        candidates = [item for item in raw_type if item != "null"]
        raw_type = candidates[0] if candidates else "string"
    if raw_type == "integer":
        return int, nullable
    if raw_type == "number":
        return float, nullable
    if raw_type == "boolean":
        return bool, nullable
    if raw_type == "array":
        return list[Any], nullable
    if raw_type == "object":
        return dict[str, Any], nullable
    if raw_type == "string":
        return str, nullable
    return Any, nullable


def args_schema_from_mcp_input_schema(
    tool_name: str,
    schema: dict[str, Any] | None,
) -> type[BaseModel]:
    """Build a Pydantic args model from an MCP tool ``inputSchema`` for LangChain."""

    suffix = _safe_model_suffix(tool_name)
    model_config = ConfigDict(extra="allow")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return create_model(f"McpToolArgs_{suffix}", __config__=model_config)

    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return create_model(f"McpToolArgs_{suffix}", __config__=model_config)

    required = {str(item) for item in (schema.get("required") or [])}
    fields: dict[str, Any] = {}
    for key, raw_prop in props.items():
        if not isinstance(key, str) or not key.strip():
            continue
        prop = raw_prop if isinstance(raw_prop, dict) else {}
        py_type, nullable = _json_schema_property_type(prop)
        optional = key not in required or nullable
        if optional:
            field_type: Any = py_type | None
            default: Any = None
        else:
            field_type = py_type
            default = ...
        description = prop.get("description")
        if isinstance(description, str) and description.strip():
            fields[key] = (field_type, Field(default=default, description=description))
        else:
            fields[key] = (field_type, default)

    if not fields:
        return create_model(f"McpToolArgs_{suffix}", __config__=model_config)
    return create_model(f"McpToolArgs_{suffix}", __config__=model_config, **fields)


def _make_mcp_tool_coroutine(session: ClientSession, tool_name: str):
    """Return an async callable that forwards validated kwargs to ``call_tool``."""

    async def _call_tool(**kwargs: Any) -> str:
        args = {key: value for key, value in kwargs.items() if value is not None}
        result = await session.call_tool(tool_name, args)
        return format_mcp_call_tool_result(result)

    return _call_tool


async def open_mcp_client_bundle(snapshot: McpClientSnapshot) -> OpenMcpClientBundle | None:
    """Open one MCP client session for an enabled snapshot."""

    stack = AsyncExitStack()
    try:
        session = await stack.enter_async_context(
            open_mcp_client_session(
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
        input_schema = getattr(mcp_tool, "inputSchema", None)
        schema_dict = input_schema if isinstance(input_schema, dict) else {}
        args_schema = args_schema_from_mcp_input_schema(original, schema_dict)
        call_tool = _make_mcp_tool_coroutine(bundle.session, original)
        tools.append(
            StructuredTool(
                name=lc_name,
                description=description,
                coroutine=call_tool,
                args_schema=args_schema,
            )
        )
    return tools


async def load_langchain_tools_for_snapshots(
    snapshots: list[McpClientSnapshot],
) -> tuple[list[StructuredTool], list[OpenMcpClientBundle], list[str]]:
    """Open all snapshots and aggregate LangChain tools (failures are skipped)."""

    all_tools: list[StructuredTool] = []
    bundles: list[OpenMcpClientBundle] = []
    unavailable: list[str] = []
    seen_names: set[str] = set()
    for snapshot in snapshots:
        if not snapshot.enabled:
            continue
        bundle = await open_mcp_client_bundle(snapshot)
        if bundle is None:
            unavailable.append(snapshot.name)
            continue
        bundles.append(bundle)
        for tool in await build_langchain_tools_from_bundle(bundle):
            if tool.name in seen_names:
                continue
            seen_names.add(tool.name)
            all_tools.append(tool)
    return all_tools, bundles, unavailable


async def close_mcp_client_bundles(bundles: list[OpenMcpClientBundle]) -> None:
    """Close all MCP client sessions opened for one Agent run."""

    for bundle in bundles:
        try:
            await bundle.stack.aclose()
        except Exception:
            log.exception("failed to close MCP client name={}", bundle.snapshot.name)
