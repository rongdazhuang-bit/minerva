# MCP 客户端资源探索器（Resource Explorer）设计说明

**日期**：2026-07-02  
**状态**：已实现  
**范围**：在现有 MCP 工具探索全屏 Modal 内增加 Resources Tab；支持 list resources、查看元数据、read resource；所有工作区成员可用。

**关系**：扩展 `docs/superpowers/specs/2026-06-18-mcp-tool-explorer-design.md`；复用 `client_explorer` 短连接会话与 `open_mcp_client_session`；Tools Tab 行为不变。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `McpToolExplorerModal` **顶部**增加 Ant Design `Tabs`：**Resources** / **Tools**。
- **Tools Tab**：保持现有行为（打开 Modal 自动 `list_tools`、List Tools 刷新、Run Tool 等）。
- **Resources Tab**：
  - 左侧：可搜索的资源列表；**List Resources** / **Clear** 按钮。
  - 右侧：展示选中资源的 **uri、name、description、mimeType**（只读）。
  - **Read Resource** 按钮读取内容；下方结果区展示文本或 JSON（样式与 Tools 的 Run Tool 结果区一致）。
- 首次切换到 Resources Tab 时**自动** `list_resources`；保留 List Resources 用于手动刷新。

### 1.2 成功标准

- member 可在不编辑客户端配置的前提下，对任意已保存客户端 list / read resources。
- 连接失败时展示明确错误，用户可通过 List Resources 重试。
- STDIO / SSE / STREAMABLE_HTTP 三种 transport 均可探索（与 Tools 一致）。
- 客户端 `enabled=false` 仍可探索（仅调试）。
- secrets 由后端从 DB 读取，**不**通过 API 返回给前端。
- Server 返回空 resources 列表时，侧栏展示 Empty，不报错。

### 1.3 非目标（本期）

- `list_resource_templates`、`subscribe_resource` / `unsubscribe_resource`。
- 弹窗标题改名（暂保留「MCP 工具探索」；Tab 已区分 Tools / Resources）。
- 弹窗内长连接 / 连接池（每次 list 或 read 均为短连接）。
- MCP **服务端** tab 的资源探索（仅客户端）。
- 调用历史持久化、导出报告。
- 新增环境变量（超时沿用 `MCP_CONNECT_TIMEOUT`）。
- 暴露 Resource 的 `title`、`size`、`icons`、`annotations`、`meta` 等扩展字段（本期仅 uri / name / description / mimeType）。

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 单 Modal + Tab 切换** | 现有 Modal 顶部 Tabs；Tools / Resources 各自独立 state 与子面板 | **采用** |
| B. 两个独立 Modal | 客户端列表两个入口 | 重复连接逻辑，与「一个探索弹窗」不符 |
| C. 打开时一次拉取 tools + resources | 合并 API | 打开慢、浪费带宽；Resources 可能为空 |

```text
McpToolExplorerModal
    │  Tab: Tools
    │    GET  .../clients/{id}/tools
    │    POST .../clients/{id}/tools/{tool_name}/call
    │  Tab: Resources
    │    GET  .../clients/{id}/resources
    │    POST .../clients/{id}/resources/read
    ▼
mcp_client_service（读 DB 配置 + secrets）
    ▼
client_explorer（扩展 list_resources / read_resource）
    │  open_mcp_client_session
    │  initialize → list_resources / read_resource
    ▼
外部 MCP Server
```

---

## 3. 权限

| 操作 | 角色 |
|------|------|
| 看到「工具探索」按钮 | 所有 workspace member |
| List Tools / Run Tool | 所有 workspace member |
| List Resources / Read Resource | 所有 workspace member |
| 编辑 / 删除客户端 | owner / admin（不变） |

API 依赖：`require_agent_workspace`（与 list tools 一致）。

---

## 4. 后端 API

前缀：`/workspaces/{workspace_id}/mcp/clients/{client_id}`

### 4.1 `GET .../resources`

**行为**

1. 校验 `client_id` 属于当前 workspace。
2. 读取 `transport`、`config`、`secrets`（完整 secrets，不返回给前端）。
3. 短连接：`initialize` → `list_resources`（超时 `MCP_CONNECT_TIMEOUT`）。
4. 关闭连接，返回 JSON。

**响应 200 成功**

```json
{
  "ok": true,
  "resources": [
    {
      "uri": "file:///docs/api.md",
      "name": "API Docs",
      "description": "REST API reference",
      "mimeType": "text/markdown"
    }
  ]
}
```

**失败 200**（业务失败，非 5xx）

```json
{
  "ok": false,
  "resources": [],
  "error_code": "mcp.client_connect_timeout",
  "error_message": "MCP connection timed out"
}
```

**字段映射**：从 MCP SDK `Resource` 映射 `uri`（必填）、`name`、`description`、`mimeType`；缺失时为 `null`。

**列表项唯一键**：`uri`。

### 4.2 `POST .../resources/read`

**Body**

```json
{
  "uri": "file:///docs/api.md"
}
```

**行为**

1. 同上读取配置并短连接。
2. `initialize` → `read_resource(uri)`。
3. 序列化 `ReadResourceResult.contents`：每个 content block 映射为 `{ uri, mimeType, text?, blob? }`；`blob` 为 base64 字符串。

**响应 200 成功**

```json
{
  "ok": true,
  "contents": [
    {
      "uri": "file:///docs/api.md",
      "mimeType": "text/markdown",
      "text": "# API\n..."
    }
  ]
}
```

**响应 200 失败**

```json
{
  "ok": false,
  "contents": [],
  "error_code": "mcp.resource_read_failed",
  "error_message": "..."
}
```

**校验**

- `uri` 须非空字符串。
- 未知 client → 404（沿用现有 `get_client` 行为）。

### 4.3 Schema 模块（Pydantic）

新增于 `app/mcp/api/schemas.py`：

- `McpResourceOut`
- `McpListResourcesOut`
- `McpReadResourceIn`
- `McpResourceContentOut`
- `McpReadResourceOut`

### 4.4 服务层

扩展 `app/mcp/runtime/client_explorer.py`：

- `map_resource_to_out(resource) -> McpResourceOut`
- `list_resources_on_session(session) -> McpListResourcesOut`
- `serialize_read_resource_result(result) -> McpReadResourceOut`
- `read_resource_on_session(session, *, uri: str) -> McpReadResourceOut`
- `list_resources_for_client(ctx) -> McpListResourcesOut`
- `read_resource_for_client(ctx, *, uri: str) -> McpReadResourceOut`

错误码与 `list_tools_for_client` 对齐：`mcp.client_connect_timeout`、`mcp.client_stdio_failed`、`mcp.client_connect_failed`；read 专用 `mcp.resource_read_failed`。

**日志**：`get_logger(__name__)`，连接/读取失败 `log.warn`，不记录 secrets 与 resource 正文。

---

## 5. 前端

### 5.1 布局

```
┌─ MCP 工具探索 — {client} ─────────────────────────────┐
│  [ Resources ]  [ Tools ]          ← 顶部 Tabs         │
├──────────────┬──────────────────────────────────────────┤
│ 搜索框       │  右侧详情区（随 Tab 变化）                │
│ List X       │                                          │
│ Clear        │  Tools: schema 表单 + Run Tool           │
│ 列表         │  Resources: 元数据 + Read Resource       │
│              │  下方结果区（共用 CSS 类）                │
└──────────────┴──────────────────────────────────────────┘
```

- Tab 置于 Modal body **最顶部**，全宽；其下为现有左右分栏 layout。
- 默认激活 **Tools** Tab。

### 5.2 组件结构

| 文件 | 职责 |
|------|------|
| `McpToolExplorerModal.tsx` | Tab 壳、共享 layout、Tab 切换 |
| `McpToolsExplorerPanel.tsx` | 自现有 Modal 迁出的 Tools 逻辑（行为不变） |
| `McpResourcesExplorerPanel.tsx` | Resources 侧栏 + 详情 + Read |
| `mcpResourceListUtils.ts` | `filterMcpResources`、搜索高亮（镜像 `mcpToolListUtils.ts`） |

CSS：复用 `McpToolExplorerModal.css` 现有类；Resources 列表项复用 `__tool-item` 等命名或增加 `__resource-item` 别名类（样式相同即可）。

### 5.3 Resources Tab 状态

- `resources`, `selectedResource`, `search`, `readResult`, `loadingList`, `loadingRead`, `listError`.
- `loadedOnce`：是否已成功或失败地拉取过列表（用于首次 Tab 激活懒加载）。

**生命周期**

- Modal `open=true` 且默认 Tools Tab → 自动 `fetchTools()`（不变）。
- 用户切换到 Resources Tab 且 `loadedOnce=false` → 自动 `fetchResources()`。
- **List Resources**：重新 `GET .../resources`。
- **Clear**：清空选中、`readResult`（不清空 `resources` 列表）。
- Modal `onClose` → 重置两个 Tab 的状态。

### 5.4 Resources 侧栏

- 列表项主标题：优先 `name`，无则 `uri`。
- 副标题：`description`（有则显示）。
- 搜索：前端 filter `name` / `uri` / `description`（大小写不敏感，空格分词全匹配，与 Tools 一致）。
- 计数文案：`共 N 个资源` / `M / N 个资源`。
- 选中 key：`uri`。

### 5.5 Resources 右侧详情

只读展示（`Descriptions` 或等效）：

| 字段 | 来源 |
|------|------|
| URI | `resource.uri` |
| Name | `resource.name` 或 `—` |
| Description | `resource.description` 或 `—` |
| MIME Type | `resource.mimeType` 或 `—` |

**Read Resource**

- 无 destructive 二次确认（read 为只读操作）。
- 调用 `POST .../resources/read`；loading 态。
- 结果区标题：Success / Error；**复制结果** 按钮。

**结果展示规则**

1. 若 content 含 `text`：尝试 `JSON.parse` 后 pretty-print；失败则原样 `<pre>` 文本。
2. 若仅含 `blob`：展示 base64 字符串 + mimeType 提示（不自动解码二进制）。
3. 多个 content block：JSON 数组格式化展示。

### 5.6 Tools Tab

- 从现有 `McpToolExplorerModal.tsx` 原样迁出至 `McpToolsExplorerPanel.tsx`。
- 侧栏按钮文案保持 **List Tools** / **Clear**；行为不变。

### 5.7 API 客户端

`frontend/src/api/mcp.ts` 新增：

```typescript
export type McpResource = {
  uri: string
  name: string | null
  description: string | null
  mimeType: string | null
}

export type McpListResourcesResult = { ok: boolean; resources: McpResource[]; ... }
export type McpReadResourceResult = { ok: boolean; contents: Array<{ uri; mimeType?; text?; blob? }>; ... }

listMcpClientResources(workspaceId, clientId)
readMcpClientResource(workspaceId, clientId, uri)
```

### 5.8 i18n

键前缀 `mcp.toolExplorer.*`（zh-CN / en.json）扩展：

| 键 | 中文示例 |
|----|----------|
| `tabTools` | Tools |
| `tabResources` | Resources |
| `listResources` | List Resources |
| `readResource` | Read Resource |
| `selectResource` | 请从左侧选择一个资源 |
| `searchResourcesPlaceholder` | 搜索资源 |
| `resourceCount` | 共 {{total}} 个资源 |
| `searchResourceCount` | {{matched}} / {{total}} 个资源 |
| `noResourceSearchMatch` | 没有匹配的资源 |
| `listResourcesFailed` | 获取资源列表失败 |
| `readResourceFailed` | 读取资源失败 |
| `resourceResultSuccess` | Resource Result: Success |
| `resourceResultError` | Resource Result: Error |
| `resourceUri` | URI |
| `resourceName` | Name |
| `resourceDescription` | Description |
| `resourceMimeType` | MIME Type |

---

## 6. 错误与边界

| 场景 | 处理 |
|------|------|
| 连接超时 | `ok: false` + Alert；可 List Resources 重试 |
| STDIO 进程失败 | `mcp.client_stdio_failed` |
| Server 不支持 resources | `ok: false` 或空 `resources` + 明确 message |
| read 失败 | `ok: false` + 结果区 Error + messageApi |
| 空 resources 列表 | Empty 组件，非错误 |
| Tab 切换 | 各 Tab loading 独立，互不取消对方请求 |
| 重复 uri | 以 uri 为 React key；若重复则追加 index 后缀（防御性） |

---

## 7. 测试建议

**后端**

- 单元测试：mock `ClientSession.list_resources` / `read_resource`，验证 schema 映射、text/blob 序列化、错误码。
- 文件：`backend/tests/test_mcp_client_explorer.py`（扩展，与 tools 测试同文件）。

**前端**

- 单元测试：`filterMcpResources`（`mcpResourceListUtils.test.ts` 或同级）。
- 手动：有 resources 的 MCP Server；空列表；read text / blob；Tab 切换 state 隔离；List Resources 刷新。

---

## 8. 对 Tool Explorer spec 的修订

`2026-06-18-mcp-tool-explorer-design.md` 范围扩展为「Tools + Resources 双 Tab 探索」；Tools 单独行为仍以原 spec §5 为准，本 spec 仅描述 **增量**（Resources Tab + 新 API）。原 CRUD / Registry / Agent Run 行为不变。

---

## 9. 实现对照（以代码为准，2026-07-02）

| 条目 | 代码位置 | 状态 |
|------|----------|------|
| GET list resources | `backend/app/mcp/api/router.py` → `mcp_client_service.list_client_resources` → `client_explorer.list_resources_for_client` | 已实现 |
| POST read resource | 同上 → `read_client_resource` → `read_resource_for_client` | 已实现 |
| Tab + Resources UI | `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx` + `McpResourcesExplorerPanel.tsx` | 已实现 |
| Tools 面板拆分 | `frontend/src/features/agent/mcp/McpToolsExplorerPanel.tsx` | 已实现 |
| API 类型 | `frontend/src/api/mcp.ts` | 已实现 |
| 资源列表工具 | `frontend/src/features/agent/mcp/mcpResourceListUtils.ts` | 已实现 |
| 单元测试 | `backend/tests/test_mcp_client_explorer.py` | 已实现 |
| MCP SDK v2 字段映射 | `client_explorer.map_resource_to_out` / `serialize_read_resource_result` | 已实现（2026-08-20）：`mime_type` 等 snake_case → API camelCase |
