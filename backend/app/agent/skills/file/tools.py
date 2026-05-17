"""File skill tools (``register_tools`` + JSON ok/error contract)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import tool

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.infrastructure.skill_tool_context import SkillToolContext

_SandboxAsyncFn = Callable[[AgentFileSandbox], Awaitable[dict[str, object]]]


async def _json_call(workspace_id: uuid.UUID, fn: _SandboxAsyncFn) -> str:
    """Run one sandbox coroutine and return a JSON string payload."""

    try:
        box = AgentFileSandbox(workspace_id=workspace_id)
        result = await fn(box)
        return json.dumps(result, ensure_ascii=False)
    except AgentFileSandbox.Error as e:
        return json.dumps(e.to_dict(), ensure_ascii=False)


def register_tools(ctx: SkillToolContext) -> list[Any]:
    """Register workspace-scoped file sandbox tools (skills ``register_tools`` convention)."""

    workspace_id = ctx.workspace_id

    @tool
    async def list_dir(path: str = "") -> str:
        """列出沙箱目录下的直接子项。path 为空表示沙箱根目录。"""

        return await _json_call(workspace_id, lambda b: b.list_dir_async(path))

    @tool
    async def read_file(path: str) -> str:
        """读取沙箱内 UTF-8 文本文件。"""

        return await _json_call(workspace_id, lambda b: b.read_file_async(path))

    @tool
    async def write_file(path: str, content: str, create_parents: bool = True) -> str:
        """在沙箱内创建或覆盖写入 UTF-8 文本文件。"""

        return await _json_call(
            workspace_id,
            lambda b: b.write_file_async(path, content, create_parents=create_parents),
        )

    @tool
    async def delete_path(path: str, recursive: bool = False) -> str:
        """删除沙箱内的文件或目录。"""

        return await _json_call(
            workspace_id, lambda b: b.delete_path_async(path, recursive=recursive)
        )

    @tool
    async def mkdir(path: str, parents: bool = True) -> str:
        """在沙箱内创建目录。"""

        return await _json_call(workspace_id, lambda b: b.mkdir_async(path, parents=parents))

    @tool
    async def move_path(src: str, dest: str) -> str:
        """在沙箱内移动或重命名文件/目录。"""

        return await _json_call(workspace_id, lambda b: b.move_path_async(src, dest))

    return [list_dir, read_file, write_file, delete_path, mkdir, move_path]
