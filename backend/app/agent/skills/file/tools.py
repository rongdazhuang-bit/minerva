"""Executable tools for the ``file`` agent skill."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.infrastructure.tool_registry import ToolRegistry

_SandboxAsyncFn = Callable[[AgentFileSandbox], Awaitable[dict[str, object]]]


async def _json_call(
    ctx: SkillToolContext | None,
    fn: _SandboxAsyncFn,
) -> str:
    """Run one sandbox coroutine and return a JSON string payload."""

    if ctx is None:
        return json.dumps(
            {
                "ok": False,
                "code": "no_workspace_context",
                "error": "workspace context is required",
            },
            ensure_ascii=False,
        )
    try:
        box = AgentFileSandbox(workspace_id=ctx.workspace_id)
        result = await fn(box)
        return json.dumps(result, ensure_ascii=False)
    except AgentFileSandbox.Error as e:
        return json.dumps(e.to_dict(), ensure_ascii=False)


def register(registry: ToolRegistry, ctx: SkillToolContext | None = None) -> None:
    """Register file sandbox tools on ``registry``."""

    async def list_dir(path: str = "") -> str:
        """List direct children under ``path``."""

        return await _json_call(ctx, lambda b: b.list_dir_async(path))

    async def read_file(path: str) -> str:
        """Read UTF-8 text from ``path``."""

        return await _json_call(ctx, lambda b: b.read_file_async(path))

    async def write_file(
        path: str,
        content: str,
        create_parents: bool = True,
    ) -> str:
        """Write UTF-8 text to ``path``."""

        return await _json_call(
            ctx,
            lambda b: b.write_file_async(path, content, create_parents=create_parents),
        )

    async def delete_path(path: str, recursive: bool = False) -> str:
        """Delete file or directory at ``path``."""

        return await _json_call(ctx, lambda b: b.delete_path_async(path, recursive=recursive))

    async def mkdir(path: str, parents: bool = True) -> str:
        """Create directory at ``path``."""

        return await _json_call(ctx, lambda b: b.mkdir_async(path, parents=parents))

    async def move_path(src: str, dest: str) -> str:
        """Move or rename ``src`` to ``dest``."""

        return await _json_call(ctx, lambda b: b.move_path_async(src, dest))

    registry.register(
        "list_dir",
        list_dir,
        description="列出工作区沙箱目录下的直接子项（文件或文件夹）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对沙箱根的路径；空字符串表示根目录。",
                },
            },
        },
    )
    registry.register(
        "read_file",
        read_file,
        description="读取沙箱内 UTF-8 文本文件内容。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径。"},
            },
            "required": ["path"],
        },
    )
    registry.register(
        "write_file",
        write_file,
        description="在沙箱内创建或覆盖写入 UTF-8 文本文件。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径。"},
                "content": {"type": "string", "description": "文件正文。"},
                "create_parents": {
                    "type": "boolean",
                    "description": "是否自动创建父目录。",
                },
            },
            "required": ["path", "content"],
        },
    )
    registry.register(
        "delete_path",
        delete_path,
        description="删除沙箱内的文件或目录。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径。"},
                "recursive": {
                    "type": "boolean",
                    "description": "删除非空目录时为 true。",
                },
            },
            "required": ["path"],
        },
    )
    registry.register(
        "mkdir",
        mkdir,
        description="在沙箱内创建目录。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对路径。"},
                "parents": {
                    "type": "boolean",
                    "description": "是否创建中间父目录。",
                },
            },
            "required": ["path"],
        },
    )
    registry.register(
        "move_path",
        move_path,
        description="在沙箱内移动或重命名文件/目录（目标父目录须已存在）。",
        parameters={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源相对路径。"},
                "dest": {"type": "string", "description": "目标相对路径。"},
            },
            "required": ["src", "dest"],
        },
    )
