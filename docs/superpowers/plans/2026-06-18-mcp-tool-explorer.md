# MCP 客户端工具探索器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MCP 客户端列表增加「工具探索」入口，全屏 Modal 内 list tools、按 schema 填参、call tool 并展示 JSON 结果；所有 workspace member 可用。

**Architecture:** 后端新增 `client_explorer` 模块，复用 `McpConnectionTester` 的短连接会话；`GET/POST` API 读 DB 配置（含 secrets，不返回前端）；前端 `McpToolExplorerModal` 左右分栏，表单/JSON 双模式，destructive 工具用 `Popconfirm` 二次确认。

**Tech Stack:** FastAPI、Pydantic、官方 `mcp` Python SDK、React、Ant Design Modal/Popconfirm、TanStack Query

**Spec:** [`docs/superpowers/specs/2026-06-18-mcp-tool-explorer-design.md`](../specs/2026-06-18-mcp-tool-explorer-design.md)

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| 路径 | 动作 | 职责 |
|------|------|------|
| `backend/app/mcp/runtime/connection_tester.py` | 修改 | 导出 `open_mcp_client_session` 供 explorer 复用 |
| `backend/app/mcp/runtime/client_explorer.py` | 创建 | `list_tools` / `call_tool` 短连接逻辑 |
| `backend/app/mcp/api/schemas.py` | 修改 | Tool explorer 请求/响应模型 |
| `backend/app/mcp/service/mcp_client_service.py` | 修改 | 按 client_id 读 DB 并委托 explorer |
| `backend/app/mcp/api/router.py` | 修改 | `GET .../tools`、`POST .../tools/{tool_name}/call` |
| `backend/tests/test_mcp_client_explorer.py` | 创建 | explorer 单元测试（mock session） |
| `frontend/src/api/mcp.ts` | 修改 | API 类型与 fetch 函数 |
| `frontend/src/features/agent/mcp/schemaFormUtils.ts` | 创建 | JSON Schema → 表单字段辅助 |
| `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx` | 创建 | 全屏工具探索 UI |
| `frontend/src/features/agent/mcp/McpToolExplorerModal.css` | 创建 | 全屏 Modal + 分栏样式 |
| `frontend/src/features/agent/mcp/AgentMcpPage.tsx` | 修改 | 操作列入口 + Modal 状态 |
| `frontend/src/i18n/locales/zh-CN.json` | 修改 | `mcp.toolExplorer.*` 文案 |
| `frontend/src/i18n/locales/en.json` | 修改 | 同上英文 |
| `docs/superpowers/specs/2026-06-18-mcp-tool-explorer-design.md` | 修改 | §9 实现对照回填 |

---

### Task 1: 共享 MCP 会话上下文

**Files:**
- Modify: `backend/app/mcp/runtime/connection_tester.py`
- Modify: `backend/app/mcp/runtime/client_bridge.py`

- [ ] **Step 1: 在 `connection_tester.py` 顶部模块级新增公开函数**

在 `McpConnectionTester` 类**之前**添加：

```python
@asynccontextmanager
async def open_mcp_client_session(
    *,
    transport: str,
    config: dict[str, Any],
    secrets: dict[str, Any],
) -> AsyncIterator[ClientSession]:
    """Yield an MCP ``ClientSession`` for one transport (not yet initialized)."""

    tester = McpConnectionTester()
    async with tester._open_session(
        transport=transport,
        config=config,
        secrets=secrets,
    ) as session:
        yield session
```

- [ ] **Step 2: 更新 `client_bridge.py` 使用公开函数**

将 `open_mcp_client_bundle` 内：

```python
        tester = McpConnectionTester()
        session = await stack.enter_async_context(
            tester._open_session(
                transport=snapshot.transport,
                config=snapshot.config,
                secrets=snapshot.secrets,
            )
        )
```

替换为：

```python
        from app.mcp.runtime.connection_tester import open_mcp_client_session

        session = await stack.enter_async_context(
            open_mcp_client_session(
                transport=snapshot.transport,
                config=snapshot.config,
                secrets=snapshot.secrets,
            )
        )
```

（import 可移到文件顶部。）

- [ ] **Step 3: 验证 import**

Run:

```bash
cd backend && python -c "from app.mcp.runtime.connection_tester import open_mcp_client_session; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/runtime/connection_tester.py backend/app/mcp/runtime/client_bridge.py
git commit -m "refactor(mcp): expose open_mcp_client_session for reuse"
```

---

### Task 2: `client_explorer` 核心逻辑

**Files:**
- Create: `backend/app/mcp/runtime/client_explorer.py`
- Create: `backend/tests/test_mcp_client_explorer.py`

- [ ] **Step 1: 写失败测试（mock session）**

创建 `backend/tests/test_mcp_client_explorer.py`：

```python
"""Unit tests for MCP client tool explorer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.runtime.client_explorer import (
    call_tool_on_session,
    list_tools_on_session,
    map_tool_to_out,
    serialize_call_tool_result,
)


def test_map_tool_to_out_defaults_annotations():
    tool = SimpleNamespace(
        name="demo",
        description="desc",
        inputSchema={"type": "object"},
        annotations=None,
    )
    out = map_tool_to_out(tool)
    assert out.name == "demo"
    assert out.annotations.readOnlyHint is False
    assert out.annotations.destructiveHint is False


def test_serialize_call_tool_result_structured():
    result = SimpleNamespace(
        structuredContent={"id": 1},
        content=[],
        isError=False,
    )
    out = serialize_call_tool_result(result)
    assert out.ok is True
    assert out.structuredContent == {"id": 1}
    assert out.isError is False


@pytest.mark.asyncio
async def test_list_tools_on_session():
    fake_tool = SimpleNamespace(
        name="t1",
        description=None,
        inputSchema={},
        annotations=SimpleNamespace(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    session = AsyncMock()
    session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[fake_tool]))
    result = await list_tools_on_session(session)
    assert result.ok is True
    assert len(result.tools) == 1
    assert result.tools[0].annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_call_tool_on_session():
    session = AsyncMock()
    session.call_tool = AsyncMock(
        return_value=SimpleNamespace(
            structuredContent={"ok": True},
            content=[],
            isError=False,
        )
    )
    result = await call_tool_on_session(session, tool_name="t1", arguments={"a": 1})
    assert result.ok is True
    session.call_tool.assert_awaited_once_with("t1", {"a": 1})
```

Run:

```bash
cd backend && pytest tests/test_mcp_client_explorer.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 2: 实现 `client_explorer.py`**

```python
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
    try:
        async with asyncio.timeout(timeout):
            async with open_mcp_client_session(
                transport=ctx.transport,
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
        log.warn("mcp list_tools failed transport={}", ctx.transport, exc_info=True)
        code = (
            "mcp.client_stdio_failed"
            if ctx.transport == "STDIO"
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
    try:
        async with asyncio.timeout(timeout):
            async with open_mcp_client_session(
                transport=ctx.transport,
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
```

- [ ] **Step 3: 在 `schemas.py` 追加模型（Task 3 会与 router 一起用；此处测试依赖，先加）**

在 `backend/app/mcp/api/schemas.py` 末尾追加：

```python
class McpToolAnnotationOut(BaseModel):
    readOnlyHint: bool = False
    destructiveHint: bool = False
    idempotentHint: bool = False
    openWorldHint: bool = False


class McpToolOut(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    annotations: McpToolAnnotationOut = Field(default_factory=McpToolAnnotationOut)


class McpListToolsOut(BaseModel):
    ok: bool
    tools: list[McpToolOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class McpCallToolIn(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpCallToolOut(BaseModel):
    ok: bool
    content: list[dict[str, Any]] = Field(default_factory=list)
    structuredContent: dict[str, Any] | None = None
    isError: bool = False
    error_code: str | None = None
    error_message: str | None = None
```

- [ ] **Step 4: 运行测试**

Run:

```bash
cd backend && pytest tests/test_mcp_client_explorer.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/runtime/client_explorer.py backend/app/mcp/api/schemas.py backend/tests/test_mcp_client_explorer.py
git commit -m "feat(mcp): add client explorer list/call helpers"
```

---

### Task 3: Service 层与 REST 路由

**Files:**
- Modify: `backend/app/mcp/service/mcp_client_service.py`
- Modify: `backend/app/mcp/api/router.py`

- [ ] **Step 1: 在 `mcp_client_service.py` 追加**

```python
from app.mcp.runtime.client_explorer import (
    McpExplorerContext,
    call_tool_for_client,
    list_tools_for_client,
)
from app.mcp.api.schemas import McpCallToolOut, McpListToolsOut


def _explorer_context_from_row(row: SysMcpClient) -> McpExplorerContext:
    """Build explorer context from a persisted client row."""

    return McpExplorerContext(
        transport=row.transport,
        config=dict(row.config or {}),
        secrets=dict(row.secrets or {}),
    )


async def list_client_tools(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> McpListToolsOut:
    """List MCP tools for one saved client configuration."""

    row = await mcp_repo.get_client(
        session, workspace_id=workspace_id, client_id=client_id
    )
    if row is None:
        raise AppError("mcp.client_not_found", "MCP client not found", 404)
    return await list_tools_for_client(_explorer_context_from_row(row))


async def call_client_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    tool_name: str,
    arguments: dict[str, Any],
) -> McpCallToolOut:
    """Call one MCP tool for a saved client configuration."""

    name = (tool_name or "").strip()
    if not name:
        raise AppError("mcp.invalid_tool_name", "tool_name is required", 400)
    row = await mcp_repo.get_client(
        session, workspace_id=workspace_id, client_id=client_id
    )
    if row is None:
        raise AppError("mcp.client_not_found", "MCP client not found", 404)
    if not isinstance(arguments, dict):
        raise AppError("mcp.invalid_arguments", "arguments must be a JSON object", 400)
    return await call_tool_for_client(
        _explorer_context_from_row(row),
        tool_name=name,
        arguments=arguments,
    )
```

（若 `get_client` 已抛 404 则沿用现有行为，删除重复的 `if row is None`。）

- [ ] **Step 2: 在 `router.py` 追加路由**

imports 增加：

```python
from app.mcp.api.schemas import (
    ...
    McpCallToolIn,
    McpCallToolOut,
    McpListToolsOut,
)
```

在 delete client 路由之后追加：

```python
@router.get("/clients/{client_id}/tools", response_model=McpListToolsOut)
async def list_mcp_client_tools(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> McpListToolsOut:
    return await client_svc.list_client_tools(
        session, workspace_id=workspace_id, client_id=client_id
    )


@router.post(
    "/clients/{client_id}/tools/{tool_name}/call",
    response_model=McpCallToolOut,
)
async def call_mcp_client_tool(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    tool_name: str,
    body: McpCallToolIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> McpCallToolOut:
    return await client_svc.call_client_tool(
        session,
        workspace_id=workspace_id,
        client_id=client_id,
        tool_name=tool_name,
        arguments=body.arguments,
    )
```

- [ ] **Step 3: 手动 smoke（可选，需本地 MCP Server）**

Run backend，member token 调用：

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/workspaces/$WS/mcp/clients/$CLIENT_ID/tools"
```

Expected: JSON `{ "ok": true|false, "tools": [...] }`

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/service/mcp_client_service.py backend/app/mcp/api/router.py
git commit -m "feat(mcp): add list-tools and call-tool REST endpoints"
```

---

### Task 4: 前端 API 客户端

**Files:**
- Modify: `frontend/src/api/mcp.ts`

- [ ] **Step 1: 追加类型**

```typescript
export type McpToolAnnotation = {
  readOnlyHint: boolean
  destructiveHint: boolean
  idempotentHint: boolean
  openWorldHint: boolean
}

export type McpTool = {
  name: string
  description: string | null
  inputSchema: Record<string, unknown>
  annotations: McpToolAnnotation
}

export type McpListToolsResult = {
  ok: boolean
  tools: McpTool[]
  error_code?: string | null
  error_message?: string | null
}

export type McpCallToolResult = {
  ok: boolean
  content?: Array<{ type: string; text: string }>
  structuredContent?: Record<string, unknown> | null
  isError?: boolean
  error_code?: string | null
  error_message?: string | null
}
```

- [ ] **Step 2: 追加 fetch 函数**

```typescript
export function listMcpClientTools(workspaceId: string, clientId: string) {
  return apiJson<McpListToolsResult>(
    `/workspaces/${workspaceId}/mcp/clients/${clientId}/tools`,
  )
}

export function callMcpClientTool(
  workspaceId: string,
  clientId: string,
  toolName: string,
  arguments_: Record<string, unknown>,
) {
  return apiJson<McpCallToolResult>(
    `/workspaces/${workspaceId}/mcp/clients/${clientId}/tools/${encodeURIComponent(toolName)}/call`,
    {
      method: 'POST',
      body: JSON.stringify({ arguments: arguments_ }),
    },
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/mcp.ts
git commit -m "feat(mcp): add tool explorer API client"
```

---

### Task 5: JSON Schema 表单辅助

**Files:**
- Create: `frontend/src/features/agent/mcp/schemaFormUtils.ts`

- [ ] **Step 1: 创建工具函数**

```typescript
/** Helpers to map MCP tool inputSchema (JSON Schema object) to form fields. */

export type SchemaFieldKind = 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object' | 'unknown'

export type SchemaField = {
  key: string
  kind: SchemaFieldKind
  required: boolean
  description?: string
}

/** Flatten top-level object properties from inputSchema. */
export function listSchemaFields(inputSchema: Record<string, unknown> | null | undefined): SchemaField[] {
  if (!inputSchema || inputSchema.type !== 'object') return []
  const props = inputSchema.properties
  if (!props || typeof props !== 'object') return []
  const required = new Set(
    Array.isArray(inputSchema.required) ? inputSchema.required.map(String) : [],
  )
  return Object.entries(props as Record<string, Record<string, unknown>>).map(([key, schema]) => ({
    key,
    kind: resolveFieldKind(schema),
    required: required.has(key),
    description: typeof schema.description === 'string' ? schema.description : undefined,
  }))
}

function resolveFieldKind(schema: Record<string, unknown>): SchemaFieldKind {
  const t = schema.type
  if (t === 'string' || t === 'number' || t === 'integer' || t === 'boolean' || t === 'array' || t === 'object') {
    return t
  }
  return 'unknown'
}

/** Build default arguments object from field list. */
export function defaultArgumentsFromFields(fields: SchemaField[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of fields) {
    if (field.kind === 'boolean') out[field.key] = false
    else if (field.kind === 'number' || field.kind === 'integer') out[field.key] = undefined
    else if (field.kind === 'array') out[field.key] = []
    else if (field.kind === 'object') out[field.key] = {}
    else out[field.key] = ''
  }
  return out
}

export function argumentsToJsonText(args: Record<string, unknown>): string {
  return JSON.stringify(args, null, 2)
}

export function parseArgumentsJson(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('arguments must be a JSON object')
  }
  return parsed as Record<string, unknown>
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/agent/mcp/schemaFormUtils.ts
git commit -m "feat(mcp): add inputSchema form helpers"
```

---

### Task 6: 全屏 Modal 组件

**Files:**
- Create: `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx`
- Create: `frontend/src/features/agent/mcp/McpToolExplorerModal.css`

- [ ] **Step 1: 创建 CSS（复制 dataset 全屏模式并加分栏）**

`McpToolExplorerModal.css` 关键类：

```css
.minerva-mcp-tool-explorer-modal.ant-modal-wrap { overflow: hidden; }
.minerva-mcp-tool-explorer-modal .ant-modal {
  top: 0 !important;
  width: 100vw !important;
  max-width: 100vw !important;
  height: 100dvh !important;
  margin: 0 !important;
  padding: 0 !important;
}
.minerva-mcp-tool-explorer-modal .ant-modal-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.minerva-mcp-tool-explorer__layout {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
.minerva-mcp-tool-explorer__sidebar {
  width: 320px;
  flex-shrink: 0;
  border-right: 1px solid var(--minerva-border, #2a3f58);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.minerva-mcp-tool-explorer__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 20px 24px;
}
.minerva-mcp-tool-explorer__tool-item--active {
  background: rgb(255 255 255 / 6%);
}
```

（完整文件参照 `DatasetCreateWizardModal.css` 补全 `.ant-modal-container` 等 antd 6 选择器。）

- [ ] **Step 2: 创建 `McpToolExplorerModal.tsx`**

组件要点（实现时按此结构编写完整文件）：

```tsx
/** Fullscreen MCP tool list / call debugger for one saved client. */
export type McpToolExplorerModalProps = {
  open: boolean
  client: McpClientListItem | null
  workspaceId: string
  onClose: () => void
}
```

状态与行为：

- `useEffect`：`open && client` → `fetchTools()`
- `fetchTools`：`listMcpClientTools`；`loadingList`；失败 `listError`
- 左侧：`Input.Search` filter；`Button` List Tools / Clear；`List` 渲染 tools
- 右侧：选中 tool 的 Tag 四标签；`Radio.Group` 表单/JSON；表单用 `listSchemaFields` 渲染 `Form.Item`；JSON 用 `TextArea`
- Run：`Popconfirm` 包裹条件 `tool.annotations.destructiveHint`；`callMcpClientTool`
- 结果：`pre` + `JSON.stringify`；Copy 用 `navigator.clipboard.writeText`
- Modal props：`wrapClassName="minerva-mcp-tool-explorer-modal"`、`width="100%"`、`style={{ top: 0, maxWidth: '100vw', padding: 0, margin: 0 }}`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/agent/mcp/McpToolExplorerModal.tsx frontend/src/features/agent/mcp/McpToolExplorerModal.css
git commit -m "feat(mcp): add fullscreen tool explorer modal"
```

---

### Task 7: 接入 AgentMcpPage

**Files:**
- Modify: `frontend/src/features/agent/mcp/AgentMcpPage.tsx`

- [ ] **Step 1: 增加 state 与 import**

```tsx
import { ToolOutlined } from '@ant-design/icons'
import { McpToolExplorerModal } from './McpToolExplorerModal'

const [explorerClient, setExplorerClient] = useState<McpClientListItem | null>(null)
```

- [ ] **Step 2: 操作列改为始终存在（member 也见）**

将 `clientColumns` 中操作列从 `isWorkspaceManager ? [...] : []` 改为**始终**包含操作列：

```tsx
{
  title: t('common.actions', { defaultValue: '操作' }),
  render: (_: unknown, row: McpClientListItem) => (
    <Space>
      <Button
        type="link"
        icon={<ToolOutlined />}
        aria-label={t('mcp.exploreTools', { defaultValue: '工具探索' })}
        onClick={() => setExplorerClient(row)}
      />
      {isWorkspaceManager ? (
        <>
          <Button type="link" icon={<EditOutlined />} onClick={() => void openEditClient(row)} />
          <Popconfirm ...>...</Popconfirm>
        </>
      ) : null}
    </Space>
  ),
},
```

更新 `useMemo` 依赖：去掉「整列仅 admin」分支。

- [ ] **Step 3: 页面底部渲染 Modal**

```tsx
<McpToolExplorerModal
  open={explorerClient != null}
  client={explorerClient}
  workspaceId={workspaceId}
  onClose={() => setExplorerClient(null)}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/agent/mcp/AgentMcpPage.tsx
git commit -m "feat(mcp): add tool explorer entry on client list"
```

---

### Task 8: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 在根对象增加 `mcp` 节点（若尚无）**

`zh-CN.json`：

```json
"mcp": {
  "exploreTools": "工具探索",
  "toolExplorer": {
    "title": "MCP 工具探索",
    "listTools": "List Tools",
    "clear": "Clear",
    "searchPlaceholder": "搜索工具",
    "runTool": "Run Tool",
    "copyInput": "Copy Input",
    "copyResult": "复制结果",
    "formMode": "表单",
    "jsonMode": "JSON",
    "resultSuccess": "Tool Result: Success",
    "resultError": "Tool Result: Error",
    "destructiveConfirm": "该工具可能产生破坏性操作，确定继续？",
    "listFailed": "获取工具列表失败",
    "callFailed": "工具调用失败",
    "readOnly": "Read-only",
    "destructive": "Destructive",
    "idempotent": "Idempotent",
    "openWorld": "Open-world"
  }
}
```

`en.json` 对应英文。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "i18n(mcp): add tool explorer strings"
```

---

### Task 9: 文档回填与验收

**Files:**
- Modify: `docs/superpowers/specs/2026-06-18-mcp-tool-explorer-design.md`

- [ ] **Step 1: 更新 §9 实现对照为已实现并填代码路径**

- [ ] **Step 2: 手动验收清单**

1. member 账号：客户端列表可见「工具探索」，不可见编辑/删除。
2. 打开 Modal 自动 list tools；List Tools 可刷新；Clear 清空选中与结果。
3. 选工具 → 表单填参 → Run → JSON 结果展示。
4. destructive 工具：Run 外包 Popconfirm，确认后执行。
5. 连接失败：左侧/顶部 Alert，可重试。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-18-mcp-tool-explorer-design.md
git commit -m "docs(mcp): backfill tool explorer implementation map"
```

---

## Spec self-review（plan ↔ spec）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 所有 member 可用 | Task 7 |
| 全屏 Modal 左右分栏 | Task 6 |
| 打开自动 list + List Tools 刷新 | Task 6 |
| 表单 + JSON 切换 | Task 5, 6 |
| 无 Tool metadata | （不实现） |
| destructive Popconfirm | Task 6 |
| GET/POST API | Task 2, 3 |
| secrets 不返回前端 | Task 3（仅用 DB row） |
| disabled 客户端可探索 | Task 3（不检查 enabled） |
| STDIO/SSE/HTTP | Task 2（复用 connection_tester） |

无 TBD / TODO 占位。
