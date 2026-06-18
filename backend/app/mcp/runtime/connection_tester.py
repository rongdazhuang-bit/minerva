"""Test MCP client connectivity (handshake + list_tools) before persisting config."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings


@dataclass(frozen=True)
class McpTestResult:
    """Outcome of one MCP client connectivity probe."""

    ok: bool
    tool_names: list[str]
    error_code: str | None = None
    error_message: str | None = None


class McpConnectionTester:
    """Run a short MCP session to verify transport config and enumerate tools."""

    async def test(
        self,
        *,
        transport: str,
        config: dict[str, Any],
        secrets: dict[str, Any],
    ) -> McpTestResult:
        """Connect with the given transport and return tool names or an error."""

        transport_key = (transport or "").strip().upper()
        try:
            async with self._open_session(
                transport=transport_key,
                config=config or {},
                secrets=secrets or {},
            ) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = [tool.name for tool in listed.tools if getattr(tool, "name", None)]
                return McpTestResult(ok=True, tool_names=names)
        except TimeoutError:
            return McpTestResult(
                ok=False,
                tool_names=[],
                error_code="mcp.client_connect_timeout",
                error_message="MCP connection timed out",
            )
        except anyio.BrokenResourceError as exc:
            return McpTestResult(
                ok=False,
                tool_names=[],
                error_code="mcp.client_stdio_failed",
                error_message=str(exc) or "MCP stdio process failed",
            )
        except OSError as exc:
            code = (
                "mcp.client_stdio_failed"
                if transport_key == "STDIO"
                else "mcp.client_connect_failed"
            )
            return McpTestResult(
                ok=False,
                tool_names=[],
                error_code=code,
                error_message=str(exc) or "MCP connection failed",
            )
        except Exception as exc:
            return McpTestResult(
                ok=False,
                tool_names=[],
                error_code="mcp.client_connect_failed",
                error_message=str(exc) or "MCP connection failed",
            )

    @asynccontextmanager
    async def _open_session(
        self,
        *,
        transport: str,
        config: dict[str, Any],
        secrets: dict[str, Any],
    ) -> AsyncIterator[ClientSession]:
        """Yield an initialized MCP ``ClientSession`` for one transport."""

        timeout = float(settings.mcp_connect_timeout)
        if transport == "STDIO":
            command = str(config.get("command") or "").strip()
            if not command:
                raise ValueError("STDIO transport requires config.command")
            raw_args = config.get("args")
            args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
            raw_env = secrets.get("env") if isinstance(secrets.get("env"), dict) else {}
            env = {str(k): str(v) for k, v in raw_env.items()}
            cwd = config.get("cwd")
            params = StdioServerParameters(
                command=command,
                args=args,
                env=env or None,
                cwd=str(cwd).strip() if cwd else None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    yield session
            return

        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError(f"{transport} transport requires config.url")
        raw_headers = secrets.get("headers") if isinstance(secrets.get("headers"), dict) else {}
        headers = {str(k): str(v) for k, v in raw_headers.items()} or None

        if transport == "SSE":
            async with sse_client(url, headers=headers, timeout=timeout) as (read, write):
                async with ClientSession(read, write) as session:
                    yield session
            return

        if transport == "STREAMABLE_HTTP":
            async with streamablehttp_client(
                url,
                headers=headers,
                timeout=timeout,
            ) as streams:
                read, write, _get_session_id = streams
                async with ClientSession(read, write) as session:
                    yield session
            return

        raise ValueError(f"Unsupported MCP transport: {transport}")
