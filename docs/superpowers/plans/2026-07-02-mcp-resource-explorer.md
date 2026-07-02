# MCP 客户端资源探索器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 MCP 工具探索全屏 Modal 顶部增加 Resources / Tools Tab；后端新增 list/read resource API；Resources Tab 支持侧栏列表、元数据展示与 Read Resource 结果区。

**Architecture:** 后端在 `client_explorer.py` 镜像 tools 模式扩展 `list_resources` / `read_resource` 短连接；前端将现有 Tools UI 拆至 `McpToolsExplorerPanel`，新增 `McpResourcesExplorerPanel`，`McpToolExplorerModal` 仅保留 Tab 壳与 layout。

**Tech Stack:** FastAPI、Pydantic、官方 `mcp` Python SDK、React、Ant Design Tabs/Descriptions、react-i18next

**Spec:** [`docs/superpowers/specs/2026-07-02-mcp-resource-explorer-design.md`](../specs/2026-07-02-mcp-resource-explorer-design.md)

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| 路径 | 动作 | 职责 |
|------|------|------|
| `backend/app/mcp/api/schemas.py` | 修改 | Resource 请求/响应 Pydantic 模型 |
| `backend/app/mcp/runtime/client_explorer.py` | 修改 | `list_resources` / `read_resource` 短连接逻辑 |
| `backend/app/mcp/service/mcp_client_service.py` | 修改 | `list_client_resources` / `read_client_resource` |
| `backend/app/mcp/api/router.py` | 修改 | `GET .../resources`、`POST .../resources/read` |
| `backend/tests/test_mcp_client_explorer.py` | 修改 | resource 映射与 session 单元测试 |
| `frontend/src/api/mcp.ts` | 修改 | Resource API 类型与 fetch 函数 |
| `frontend/src/features/agent/mcp/mcpResourceListUtils.ts` | 创建 | 资源列表 filter / 高亮 |
| `frontend/src/features/agent/mcp/McpToolsExplorerPanel.tsx` | 创建 | 自 Modal 迁出的 Tools 面板 |
| `frontend/src/features/agent/mcp/McpResourcesExplorerPanel.tsx` | 创建 | Resources 侧栏 + 详情 + Read |
| `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx` | 修改 | Tab 壳，渲染两个 Panel |
| `frontend/src/features/agent/mcp/McpToolExplorerModal.css` | 修改 | Tab 栏样式（可选微调） |
| `frontend/src/i18n/locales/zh-CN.json` | 修改 | `mcp.toolExplorer.*` 扩展 |
| `frontend/src/i18n/locales/en.json` | 修改 | 同上英文 |
| `docs/superpowers/specs/2026-07-02-mcp-resource-explorer-design.md` | 修改 | §9 实现对照回填 |

---

### Task 1: Resource Pydantic schemas

**Files:**
- Modify: `backend/app/mcp/api/schemas.py`

- [ ] **Step 1: 在 `McpCallToolOut` 之后追加模型**

```python
class McpResourceOut(BaseModel):
    """One MCP resource entry from ``list_resources``."""

    uri: str
    name: str | None = None
    description: str | None = None
    mimeType: str | None = None


class McpListResourcesOut(BaseModel):
    """Result of listing MCP resources for one client."""

    ok: bool
    resources: list[McpResourceOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class McpReadResourceIn(BaseModel):
    """Body for reading one MCP resource by URI."""

    uri: str


class McpResourceContentOut(BaseModel):
    """One content block from ``read_resource``."""

    uri: str
    mimeType: str | None = None
    text: str | None = None
    blob: str | None = None


class McpReadResourceOut(BaseModel):
    """Result of reading one MCP resource."""

    ok: bool
    contents: list[McpResourceContentOut] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
```

- [ ] **Step 2: 验证 import**

Run:

```bash
cd backend; python -c "from app.mcp.api.schemas import McpListResourcesOut, McpReadResourceOut; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/mcp/api/schemas.py
git commit -m "feat(mcp): add resource explorer API schemas"
```

---

### Task 2: `client_explorer` resource 逻辑（TDD）

**Files:**
- Modify: `backend/app/mcp/runtime/client_explorer.py`
- Modify: `backend/tests/test_mcp_client_explorer.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_mcp_client_explorer.py` 追加 import 与测试：

```python
from app.mcp.runtime.client_explorer import (
    call_tool_on_session,
    list_resources_on_session,
    list_tools_on_session,
    map_resource_to_out,
    map_tool_to_out,
    read_resource_on_session,
    serialize_call_tool_result,
    serialize_read_resource_result,
)


def test_map_resource_to_out():
    resource = SimpleNamespace(
        uri="file:///a.md",
        name="Doc",
        description="hello",
        mimeType="text/markdown",
    )
    out = map_resource_to_out(resource)
    assert out.uri == "file:///a.md"
    assert out.name == "Doc"
    assert out.mimeType == "text/markdown"


def test_serialize_read_resource_result_text():
    result = SimpleNamespace(
        contents=[
            SimpleNamespace(
                uri="file:///a.md",
                mimeType="text/plain",
                text="hello",
                blob=None,
            )
        ]
    )
    out = serialize_read_resource_result(result)
    assert out.ok is True
    assert out.contents[0].text == "hello"
    assert out.contents[0].blob is None


@pytest.mark.asyncio
async def test_list_resources_on_session():
    fake = SimpleNamespace(
        uri="file:///x",
        name="X",
        description=None,
        mimeType=None,
    )
    session = AsyncMock()
    session.list_resources = AsyncMock(return_value=SimpleNamespace(resources=[fake]))
    result = await list_resources_on_session(session)
    assert result.ok is True
    assert len(result.resources) == 1
    assert result.resources[0].uri == "file:///x"


@pytest.mark.asyncio
async def test_read_resource_on_session():
    session = AsyncMock()
    session.read_resource = AsyncMock(
        return_value=SimpleNamespace(
            contents=[
                SimpleNamespace(
                    uri="file:///x",
                    mimeType="text/plain",
                    text="body",
                    blob=None,
                )
            ]
        )
    )
    result = await read_resource_on_session(session, uri="file:///x")
    assert result.ok is True
    assert result.contents[0].text == "body"
    session.read_resource.assert_awaited_once_with("file:///x")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend; pytest tests/test_mcp_client_explorer.py -v -k resource
```

Expected: FAIL（`ImportError` 或函数未定义）

- [ ] **Step 3: 实现 resource 函数**

在 `backend/app/mcp/runtime/client_explorer.py`：

1. 扩展 import：

```python
from app.mcp.api.schemas import (
    McpCallToolOut,
    McpListResourcesOut,
    McpListToolsOut,
    McpReadResourceOut,
    McpResourceContentOut,
    McpResourceOut,
    McpToolAnnotationOut,
    McpToolOut,
)
```

2. 在 `map_tool_to_out` 之后追加：

```python
def map_resource_to_out(resource: Any) -> McpResourceOut:
    """Map MCP SDK resource to API output model."""

    return McpResourceOut(
        uri=str(getattr(resource, "uri", "") or ""),
        name=getattr(resource, "name", None),
        description=getattr(resource, "description", None),
        mimeType=getattr(resource, "mimeType", None),
    )


async def list_resources_on_session(session: ClientSession) -> McpListResourcesOut:
    """Call ``list_resources`` on an initialized session."""

    listed = await session.list_resources()
    resources = [
        map_resource_to_out(item)
        for item in listed.resources
        if getattr(item, "uri", None)
    ]
    return McpListResourcesOut(ok=True, resources=resources)


def serialize_read_resource_result(result: Any) -> McpReadResourceOut:
    """Convert MCP ``ReadResourceResult`` to API output."""

    contents: list[McpResourceContentOut] = []
    for block in getattr(result, "contents", []) or []:
        text = getattr(block, "text", None)
        blob = getattr(block, "blob", None)
        contents.append(
            McpResourceContentOut(
                uri=str(getattr(block, "uri", "") or ""),
                mimeType=getattr(block, "mimeType", None),
                text=str(text) if text is not None else None,
                blob=str(blob) if blob is not None else None,
            )
        )
    return McpReadResourceOut(ok=True, contents=contents)


async def read_resource_on_session(
    session: ClientSession,
    *,
    uri: str,
) -> McpReadResourceOut:
    """Call ``read_resource`` on an initialized session."""

    result = await session.read_resource(uri)
    return serialize_read_resource_result(result)
```

3. 在文件末尾追加 client 级包装（镜像 `list_tools_for_client`）：

```python
async def list_resources_for_client(ctx: McpExplorerContext) -> McpListResourcesOut:
    """Open session, initialize, list resources, close."""

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
                return await list_resources_on_session(session)
    except TimeoutError:
        return McpListResourcesOut(
            ok=False,
            resources=[],
            error_code="mcp.client_connect_timeout",
            error_message="MCP connection timed out",
        )
    except anyio.BrokenResourceError as exc:
        return McpListResourcesOut(
            ok=False,
            resources=[],
            error_code="mcp.client_stdio_failed",
            error_message=str(exc) or "MCP stdio process failed",
        )
    except Exception as exc:
        log.warn("mcp list_resources failed transport={}", transport_key, exc_info=True)
        code = (
            "mcp.client_stdio_failed"
            if transport_key == "STDIO"
            else "mcp.client_connect_failed"
        )
        return McpListResourcesOut(
            ok=False,
            resources=[],
            error_code=code,
            error_message=str(exc) or "MCP connection failed",
        )


async def read_resource_for_client(
    ctx: McpExplorerContext,
    *,
    uri: str,
) -> McpReadResourceOut:
    """Open session, initialize, read resource, close."""

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
                return await read_resource_on_session(session, uri=uri)
    except TimeoutError:
        return McpReadResourceOut(
            ok=False,
            error_code="mcp.client_connect_timeout",
            error_message="MCP connection timed out",
        )
    except Exception as exc:
        log.warn("mcp read_resource failed uri={}", uri, exc_info=True)
        return McpReadResourceOut(
            ok=False,
            error_code="mcp.resource_read_failed",
            error_message=str(exc) or "MCP resource read failed",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd backend; pytest tests/test_mcp_client_explorer.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/runtime/client_explorer.py backend/tests/test_mcp_client_explorer.py
git commit -m "feat(mcp): add list/read resource explorer runtime"
```

---

### Task 3: Service 层与路由

**Files:**
- Modify: `backend/app/mcp/service/mcp_client_service.py`
- Modify: `backend/app/mcp/api/router.py`

- [ ] **Step 1: 扩展 service import 与服务函数**

在 `mcp_client_service.py` import 区追加：

```python
from app.mcp.api.schemas import McpCallToolOut, McpListResourcesOut, McpListToolsOut, McpReadResourceOut
from app.mcp.runtime.client_explorer import (
    call_tool_for_client,
    list_resources_for_client,
    list_tools_for_client,
    read_resource_for_client,
)
```

在 `call_client_tool` 之后追加：

```python
async def list_client_resources(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
) -> McpListResourcesOut:
    """List MCP resources for one saved client configuration."""

    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await list_resources_for_client(_explorer_context_from_row(row))


async def read_client_resource(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    uri: str,
) -> McpReadResourceOut:
    """Read one MCP resource for a saved client configuration."""

    target_uri = (uri or "").strip()
    if not target_uri:
        raise AppError("mcp.invalid_resource_uri", "uri is required", 400)
    row = await get_client(session, workspace_id=workspace_id, client_id=client_id)
    return await read_resource_for_client(
        _explorer_context_from_row(row),
        uri=target_uri,
    )
```

- [ ] **Step 2: 注册路由**

在 `router.py` import 区追加 `McpListResourcesOut`, `McpReadResourceIn`, `McpReadResourceOut`。

在 `call_mcp_client_tool` 路由之后追加：

```python
@router.get("/clients/{client_id}/resources", response_model=McpListResourcesOut)
async def list_mcp_client_resources(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_agent_workspace),
    session: AsyncSession = Depends(get_db),
) -> McpListResourcesOut:
    return await client_svc.list_client_resources(
        session, workspace_id=workspace_id, client_id=client_id
    )


@router.post(
    "/clients/{client_id}/resources/read",
    response_model=McpReadResourceOut,
)
async def read_mcp_client_resource(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    body: McpReadResourceIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_agent_workspace),
    session: AsyncSession = Depends(get_db),
) -> McpReadResourceOut:
    return await client_svc.read_client_resource(
        session,
        workspace_id=workspace_id,
        client_id=client_id,
        uri=body.uri,
    )
```

- [ ] **Step 3: 验证路由注册**

Run:

```bash
cd backend; python -c "from app.mcp.api.router import router; paths=[r.path for r in router.routes if 'resources' in getattr(r,'path','')]; print(paths)"
```

Expected: 包含 `/clients/{client_id}/resources` 与 `/clients/{client_id}/resources/read`

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/service/mcp_client_service.py backend/app/mcp/api/router.py
git commit -m "feat(mcp): expose list/read resource API routes"
```

---

### Task 4: 前端 API 客户端

**Files:**
- Modify: `frontend/src/api/mcp.ts`

- [ ] **Step 1: 追加类型与函数**

在 `McpCallToolResult` 之后：

```typescript
export type McpResource = {
  uri: string
  name: string | null
  description: string | null
  mimeType: string | null
}

export type McpListResourcesResult = {
  ok: boolean
  resources: McpResource[]
  error_code?: string | null
  error_message?: string | null
}

export type McpResourceContent = {
  uri: string
  mimeType?: string | null
  text?: string | null
  blob?: string | null
}

export type McpReadResourceResult = {
  ok: boolean
  contents?: McpResourceContent[]
  error_code?: string | null
  error_message?: string | null
}
```

在 `callMcpClientTool` 之后：

```typescript
export function listMcpClientResources(workspaceId: string, clientId: string) {
  return apiJson<McpListResourcesResult>(`/workspaces/${workspaceId}/mcp/clients/${clientId}/resources`)
}

export function readMcpClientResource(workspaceId: string, clientId: string, uri: string) {
  return apiJson<McpReadResourceResult>(`/workspaces/${workspaceId}/mcp/clients/${clientId}/resources/read`, {
    method: 'POST',
    body: JSON.stringify({ uri }),
  })
}
```

- [ ] **Step 2: Typecheck**

Run:

```bash
cd frontend; npm run typecheck
```

Expected: 无新增类型错误（若项目无 typecheck 脚本则 `npx tsc --noEmit`）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/mcp.ts
git commit -m "feat(mcp): add resource explorer API client"
```

---

### Task 5: 资源列表工具函数

**Files:**
- Create: `frontend/src/features/agent/mcp/mcpResourceListUtils.ts`

- [ ] **Step 1: 创建 filter 与高亮（镜像 tools）**

```typescript
import type { McpResource } from '@/api/mcp'
import { splitTextHighlight, type TextHighlightPart } from './mcpToolListUtils'

export { splitTextHighlight, type TextHighlightPart }

/** Filter MCP resources by name/uri/description; all whitespace-separated tokens must match. */
export function filterMcpResources(resources: McpResource[], query: string): McpResource[] {
  const tokens = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
  if (tokens.length === 0) return resources
  return resources.filter((resource) => {
    const haystack = `${resource.name ?? ''}\n${resource.uri}\n${resource.description ?? ''}`.toLowerCase()
    return tokens.every((token) => haystack.includes(token))
  })
}

/** Display title for one resource row. */
export function resourceDisplayName(resource: McpResource): string {
  return resource.name?.trim() || resource.uri
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/agent/mcp/mcpResourceListUtils.ts
git commit -m "feat(mcp): add resource list filter utils"
```

---

### Task 6: 拆分 Tools 面板

**Files:**
- Create: `frontend/src/features/agent/mcp/McpToolsExplorerPanel.tsx`
- Modify: `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx`

- [ ] **Step 1: 创建 `McpToolsExplorerPanel.tsx`**

将 `McpToolExplorerModal.tsx` 中 `<aside>` + `<main>` 的 Tools 逻辑**整体迁出**（state、handlers、render 均移入 Panel）。

Props 接口：

```typescript
export type McpToolsExplorerPanelProps = {
  client: McpClientListItem
  workspaceId: string
}
```

Panel 内部保留现有行为：
- `open` 等效：由父组件挂载时 `useEffect` 触发 `fetchTools()`（依赖 `client.id`）。
- 侧栏：搜索、List Tools、Clear、工具列表。
- 主区：schema 表单、Run Tool、结果区。

导出组件名：`McpToolsExplorerPanel`。

- [ ] **Step 2: 暂时简化 Modal 为仅渲染 Panel（Task 8 再加 Tab）**

Modal  body 改为：

```tsx
{client ? <McpToolsExplorerPanel client={client} workspaceId={workspaceId} /> : null}
```

删除 Modal 内已迁出的 state 与函数。

- [ ] **Step 3: 手动冒烟**

打开 MCP 客户端「工具探索」，确认 Tools 行为与拆分前一致。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/agent/mcp/McpToolsExplorerPanel.tsx frontend/src/features/agent/mcp/McpToolExplorerModal.tsx
git commit -m "refactor(mcp): extract tools explorer panel component"
```

---

### Task 7: Resources 面板

**Files:**
- Create: `frontend/src/features/agent/mcp/McpResourcesExplorerPanel.tsx`

- [ ] **Step 1: 创建 Panel 骨架**

Props：

```typescript
export type McpResourcesExplorerPanelProps = {
  client: McpClientListItem
  workspaceId: string
  active: boolean
}
```

- `active`：当前 Tab 是否为 Resources；`active && !loadedOnce` 时自动 `fetchResources()`。
- State：`resources`, `selectedResource`, `search`, `readResult`, `loadingList`, `loadingRead`, `listError`, `loadedOnce`.

- [ ] **Step 2: 实现侧栏**

- 搜索框 placeholder：`mcp.toolExplorer.searchResourcesPlaceholder`
- 计数：`resourceCount` / `searchResourceCount`
- 按钮：**List Resources**（`fetchResources`）、**Clear**（清空选中与 readResult）
- 列表项：主标题 `resourceDisplayName(resource)`，副标题 `description`
- key：`resource.uri`（若重复则 `` `${uri}-${index}` ``）

- [ ] **Step 3: 实现右侧详情**

使用 `Descriptions` 展示 uri / name / description / mimeType（空值显示 `—`）。

**Read Resource** 按钮：

```typescript
const readResource = async () => {
  if (!client || !selectedResource) return
  setLoadingRead(true)
  setReadResult(null)
  try {
    const res = await readMcpClientResource(workspaceId, client.id, selectedResource.uri)
    setReadResult(res)
    if (!res.ok) {
      messageApi.error(res.error_message || t('mcp.toolExplorer.readResourceFailed', { defaultValue: '读取资源失败' }))
    }
  } catch (err) {
    messageApi.error(err instanceof Error ? err.message : t('mcp.toolExplorer.readResourceFailed', { defaultValue: '读取资源失败' }))
  } finally {
    setLoadingRead(false)
  }
}
```

- [ ] **Step 4: 实现结果展示**

```typescript
function formatResourceContents(contents: McpResourceContent[] | undefined): string {
  if (!contents?.length) return ''
  const blocks = contents.map((block) => {
    if (block.text != null) {
      try {
        return JSON.stringify(JSON.parse(block.text), null, 2)
      } catch {
        return block.text
      }
    }
    if (block.blob != null) {
      return JSON.stringify({ mimeType: block.mimeType, blob: block.blob }, null, 2)
    }
    return JSON.stringify(block, null, 2)
  })
  return blocks.length === 1 ? blocks[0] : JSON.stringify(contents, null, 2)
}
```

结果区复用 class：`minerva-mcp-tool-explorer__result`、`__result--success`、`__result--error`；标题用 `resourceResultSuccess` / `resourceResultError`；含复制按钮。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/agent/mcp/McpResourcesExplorerPanel.tsx
git commit -m "feat(mcp): add resources explorer panel"
```

---

### Task 8: Modal Tab 壳

**Files:**
- Modify: `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx`
- Modify: `frontend/src/features/agent/mcp/McpToolExplorerModal.css`

- [ ] **Step 1: 引入 Tabs 与两个 Panel**

```tsx
import { Tabs } from 'antd'
import { McpResourcesExplorerPanel } from './McpResourcesExplorerPanel'
import { McpToolsExplorerPanel } from './McpToolsExplorerPanel'

type ExplorerTab = 'tools' | 'resources'
```

Modal body：

```tsx
<div className="minerva-mcp-tool-explorer__layout">
  <Tabs
    className="minerva-mcp-tool-explorer__tabs"
    activeKey={activeTab}
    onChange={(key) => setActiveTab(key as ExplorerTab)}
    items={[
      {
        key: 'resources',
        label: t('mcp.toolExplorer.tabResources', { defaultValue: 'Resources' }),
        children: client ? (
          <McpResourcesExplorerPanel
            client={client}
            workspaceId={workspaceId}
            active={activeTab === 'resources'}
          />
        ) : null,
      },
      {
        key: 'tools',
        label: t('mcp.toolExplorer.tabTools', { defaultValue: 'Tools' }),
        children: client ? (
          <McpToolsExplorerPanel client={client} workspaceId={workspaceId} />
        ) : null,
      },
    ]}
  />
</div>
```

- 默认 `activeTab = 'tools'`。
- Modal `open` 时重置 `activeTab` 为 `'tools'`。

- [ ] **Step 2: 调整 layout CSS**

两个 Panel 内部各自包含原来的 `aside + main` 分栏。Tabs 内容区需 flex 填满：

```css
.minerva-mcp-tool-explorer__tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.minerva-mcp-tool-explorer__tabs .ant-tabs-content-holder {
  flex: 1;
  min-height: 0;
}

.minerva-mcp-tool-explorer__tabs .ant-tabs-content,
.minerva-mcp-tool-explorer__tabs .ant-tabs-tabpane {
  height: 100%;
}
```

若 Panel 根节点为 flex row（sidebar + main），确保 `height: 100%` 与 `min-height: 0` 与现有 `__layout` 规则一致。

- [ ] **Step 3: 手动冒烟**

1. 打开 Modal 默认 Tools Tab，行为不变。
2. 切 Resources Tab 自动 list；List Resources 刷新；选中 + Read Resource。
3. 切回 Tools Tab，Tools 状态保留。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/agent/mcp/McpToolExplorerModal.tsx frontend/src/features/agent/mcp/McpToolExplorerModal.css
git commit -m "feat(mcp): add Resources/Tools tabs to tool explorer modal"
```

---

### Task 9: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: zh-CN 追加键**

```json
"mcp.toolExplorer.tabTools": "Tools",
"mcp.toolExplorer.tabResources": "Resources",
"mcp.toolExplorer.listResources": "List Resources",
"mcp.toolExplorer.readResource": "Read Resource",
"mcp.toolExplorer.selectResource": "请从左侧选择一个资源",
"mcp.toolExplorer.searchResourcesPlaceholder": "搜索资源",
"mcp.toolExplorer.resourceCount": "共 {{total}} 个资源",
"mcp.toolExplorer.searchResourceCount": "{{matched}} / {{total}} 个资源",
"mcp.toolExplorer.noResourceSearchMatch": "没有匹配的资源",
"mcp.toolExplorer.listResourcesFailed": "获取资源列表失败",
"mcp.toolExplorer.readResourceFailed": "读取资源失败",
"mcp.toolExplorer.resourceResultSuccess": "Resource Result: Success",
"mcp.toolExplorer.resourceResultError": "Resource Result: Error",
"mcp.toolExplorer.resourceUri": "URI",
"mcp.toolExplorer.resourceName": "Name",
"mcp.toolExplorer.resourceDescription": "Description",
"mcp.toolExplorer.resourceMimeType": "MIME Type"
```

- [ ] **Step 2: en.json 同上（英文文案）**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "i18n(mcp): add resource explorer strings"
```

---

### Task 10: Spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-mcp-resource-explorer-design.md`

- [ ] **Step 1: 更新 §9 实现对照表**

将所有「待实现」改为「已实现」，填入实际文件路径；将文档 **状态** 改为「已实现」。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-02-mcp-resource-explorer-design.md
git commit -m "docs(mcp): backfill resource explorer implementation map"
```

---

## Manual test checklist

- [ ] member 账号可见「工具探索」入口
- [ ] Modal 默认 Tools Tab；打开自动 list tools
- [ ] Resources Tab 首次进入自动 list resources
- [ ] List Resources 刷新；空列表显示 Empty
- [ ] 选中资源展示 uri/name/description/mimeType
- [ ] Read Resource 成功/失败结果区与复制
- [ ] 连接失败 Alert + 重试
- [ ] Tab 切换后各自 state 独立（Tools 选中项不丢失）

---

## Plan self-review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| GET list resources | Task 2–3 |
| POST read resource | Task 2–3 |
| Tab Resources / Tools | Task 8 |
| Resources 侧栏 + Read | Task 7 |
| Tools 行为不变 | Task 6 |
| i18n | Task 9 |
| 单元测试 | Task 2 |
| §9 回填 | Task 10 |

无 TBD / TODO 占位；类型名 `McpResourceOut` / `McpReadResourceOut` 前后一致。
