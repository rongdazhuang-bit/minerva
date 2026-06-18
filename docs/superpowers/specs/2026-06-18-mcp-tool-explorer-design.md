# MCP 客户端工具探索器（Tool Explorer）设计说明

**日期**：2026-06-18  
**状态**：已实现  
**范围**：在 MCP 管理页「客户端」列表操作列新增入口；全屏 Modal 内 list tools、查看 schema、在线 call tool；所有工作区成员可用。

**关系**：扩展 `docs/superpowers/specs/2026-06-18-mcp-management-design.md`（原 1.3 非目标「MCP 工具在线调试 UI」由本 spec 单独实现）；复用 `McpConnectionTester` 会话逻辑与 `client_bridge` 的 `call_tool` 结果序列化。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `AgentMcpPage` MCP **客户端**表格操作列增加「工具探索」按钮，**所有 workspace member** 可见、可点击。
- 点击后打开**全屏 Modal**，布局参考 MCP Inspector：左侧工具列表 + 右侧详情/执行区。
- 打开 Modal 时**自动**连接 MCP Server 并 `list_tools`；保留「List Tools」按钮用于手动刷新。
- 选中工具后展示 name、description、annotation 标签（readOnly / destructive / idempotent / openWorld）。
- 按 `inputSchema` **自动生成表单**（required 标 `*`）；支持「表单 / JSON」模式切换。
- 支持 **Run Tool** 与 **Copy Input**；结果区展示格式化 JSON（含 `content` 与 `structuredContent`）。
- **destructive** 工具（`destructiveHint === true`）执行前须二次确认（前端 `Popconfirm`，见 Minerva 约定）。

### 1.2 成功标准

- member 可在不编辑客户端配置的前提下，对任意已保存客户端 list / call tools。
- 连接失败时展示明确错误，用户可通过 List Tools 重试。
- STDIO / SSE / STREAMABLE_HTTP 三种 transport 均可探索（与现有 test 一致）。
- 客户端 `enabled=false` 仍可探索（仅调试，不影响 Agent Run 注册逻辑）。
- secrets 由后端从 DB 读取，**不**通过 API 返回给前端。

### 1.3 非目标（本期）

- Tool-specific Metadata（`_meta` key-value，call 时不发送）。
- 弹窗内长连接 / 连接池（每次 list 或 call 均为短连接）。
- MCP **服务端** tab 的工具探索（仅客户端）。
- 调用历史持久化、导出报告。
- 新增环境变量（超时沿用 `MCP_CONNECT_TIMEOUT`）。

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 后端代理** | 新增 list-tools / call-tool API，后端短连接 MCP | **采用** |
| B. 前端直连 MCP | 浏览器连 SSE/HTTP | 密钥/CORS/STDIO 不可行 |
| C. 扩展 test 接口 | 在 `POST .../test` 上叠加 | 语义混乱，拒绝 |

```text
AgentMcpPage
    │  GET  .../clients/{id}/tools
    │  POST .../clients/{id}/tools/{tool_name}/call
    ▼
mcp_client_service（读 DB 配置 + secrets）
    ▼
McpClientExplorer（新建，或扩展现有 runtime 模块）
    │  McpConnectionTester._open_session
    │  initialize → list_tools / call_tool
    ▼
外部 MCP Server
```

---

## 3. 权限

| 操作 | 角色 |
|------|------|
| 看到「工具探索」按钮 | 所有 workspace member |
| List Tools / Run Tool | 所有 workspace member |
| 编辑 / 删除客户端 | owner / admin（不变） |

API 依赖：`require_workspace_member`（与 list clients 一致）。

---

## 4. 后端 API

前缀：`/workspaces/{workspace_id}/mcp/clients/{client_id}`

### 4.1 `GET .../tools`

**行为**

1. 校验 `client_id` 属于当前 workspace。
2. 读取 `transport`、`config`、`secrets`（完整 secrets，不返回给客户端）。
3. 短连接：`initialize` → `list_tools`（超时 `MCP_CONNECT_TIMEOUT`）。
4. 关闭连接，返回 JSON。

**响应 200**

```json
{
  "ok": true,
  "tools": [
    {
      "name": "queryWindFarmBasicInfoByShortName",
      "description": "根据风电场简称获取完整的风电场名称",
      "inputSchema": { "type": "object", "properties": { "...": {} }, "required": ["..."] },
      "annotations": {
        "readOnlyHint": false,
        "destructiveHint": true,
        "idempotentHint": false,
        "openWorldHint": true
      }
    }
  ]
}
```

**失败 200**（业务失败，非 5xx）

```json
{
  "ok": false,
  "tools": [],
  "error_code": "mcp.client_connect_timeout",
  "error_message": "MCP connection timed out"
}
```

`annotations` 字段：从 MCP SDK `Tool.annotations` 映射；缺失时各 hint 默认 `false`。

### 4.2 `POST .../tools/{tool_name}/call`

**Body**

```json
{
  "arguments": {
    "windFarmShortNames": "青洲三"
  }
}
```

**行为**

1. 同上读取配置并短连接。
2. `initialize` → `call_tool(tool_name, arguments)`。
3. 序列化结果（与 `client_bridge` 一致）：`content`（text blocks 数组）、`structuredContent`、`isError`。

**响应 200 成功**

```json
{
  "ok": true,
  "content": [{ "type": "text", "text": "..." }],
  "structuredContent": { "...": "..." },
  "isError": false
}
```

**响应 200 失败**

```json
{
  "ok": false,
  "error_code": "mcp.tool_call_failed",
  "error_message": "..."
}
```

**校验**

- `tool_name` 路径参数须非空；`arguments` 默认为 `{}`，须为 JSON object。
- 未知 client → 404（沿用现有 `get_client` 行为）。

### 4.3 Schema 模块（Pydantic）

新增于 `app/mcp/api/schemas.py`：

- `McpToolAnnotationOut`
- `McpToolOut`
- `McpListToolsOut`
- `McpCallToolIn`
- `McpCallToolOut`

### 4.4 服务层

新建 `app/mcp/runtime/client_explorer.py`（或 `service/mcp_client_explorer_service.py`）：

- `list_tools_for_client(transport, config, secrets) -> McpListToolsResult`
- `call_tool_for_client(..., tool_name, arguments) -> McpCallToolResult`

复用 `McpConnectionTester._open_session`；可将 `_open_session` 提升为模块级公开函数以避免跨类私有调用。

**日志**：`get_logger(__name__)`，连接/调用失败 `log.warn` / `log.exception`，不记录 secrets。

---

## 5. 前端

### 5.1 入口

- 文件：`frontend/src/features/agent/mcp/AgentMcpPage.tsx`
- 操作列：**独立一列或与现有操作列并列**；member 仅见「工具探索」；admin  additionally 见编辑/删除。
- 图标建议：`ToolOutlined`；文案 i18n：`mcp.exploreTools`。

### 5.2 全屏 Modal

- 新建 `McpToolExplorerModal.tsx` + `.css`（参考 `DatasetCreateWizardModal` 全屏 wrapClassName 模式）。
- Props：`open`, `client: McpClientListItem`, `onClose`.

**布局**

| 区域 | 内容 |
|------|------|
| 顶栏 | 客户端 name、transport、关闭按钮 |
| 左侧 (~320px) | 搜索框；List Tools / Clear；可滚动工具列表（name + description 摘要） |
| 右侧 | 选中工具详情、参数区、Run / Copy Input、结果 JSON |

**状态**

- `tools`, `selectedTool`, `arguments`, `inputMode: 'form' | 'json'`, `result`, `loadingList`, `loadingCall`, `listError`.

**生命周期**

- `open=true` → 自动 `fetchTools()`。
- `onClose` → 重置状态。

**List Tools**：重新 `GET .../tools`。  
**Clear**：清空选中、arguments、result（不清空 tools 列表）。

**搜索**：前端 filter `name` / `description`（大小写不敏感）。

### 5.3 参数表单

- 解析 JSON Schema `type: object` 的 `properties` / `required`。
- 支持：`string`（Input / TextArea）、`number` / `integer`、`boolean`（Switch）、`array`（JSON 文本或简单 tag 输入，复杂 array 提示切 JSON）。
- 嵌套 `object`：首期可折叠 JSON 子字段或提示切 JSON 模式。
- JSON 模式：`Input.TextArea`，校验 JSON parse 后再提交。

### 5.4 Run Tool

- 校验 arguments（表单 required 或 JSON parse）。
- 若 `annotations.destructiveHint === true`：Run 按钮外包 **`Popconfirm`**（title 说明可能产生破坏性副作用）。
- 调用 `POST .../call`；loading 态；结果区 Success / Error 标题 + 可复制 JSON。

### 5.5 API 客户端

`frontend/src/api/mcp.ts` 新增：

- `listMcpClientTools(workspaceId, clientId)`
- `callMcpClientTool(workspaceId, clientId, toolName, arguments)`

### 5.6 i18n

键前缀 `mcp.toolExplorer.*`（zh-CN / en.json）。

---

## 6. 错误与边界

| 场景 | 处理 |
|------|------|
| 连接超时 | `ok: false` + Alert；可 List Tools 重试 |
| STDIO 进程失败 | 同 test：`mcp.client_stdio_failed` |
| call 返回 `isError: true` | 仍 `ok: true`，结果区标 Error 并展示 content |
| inputSchema 缺失 | 表单区仅 JSON 模式 |
| 复杂 schema | 表单尽力渲染；Alert 提示可切 JSON |

---

## 7. 测试建议

**后端**

- 单元测试：mock `ClientSession.list_tools` / `call_tool`，验证 schema 映射与错误码。
- 集成测试（可选）：对 fixture SSE server 跑 list + call。

**前端**

- 手动：member 账号可见按钮；destructive 工具 Popconfirm；表单/JSON 切换；Copy Input。

---

## 8. 对原 MCP 管理 spec 的修订

`2026-06-18-mcp-management-design.md` §1.3 非目标「MCP 工具在线调试 UI」→ 由 **本 spec** 实现；原 CRUD / Registry / Agent Run 行为不变。

---

## 9. 实现对照（以代码为准，2026-06-18）

| 条目 | 代码位置 | 状态 |
|------|----------|------|
| GET list tools | `backend/app/mcp/api/router.py` → `mcp_client_service.list_client_tools` → `client_explorer.list_tools_for_client` | 已实现 |
| POST call tool | 同上 → `call_client_tool` → `call_tool_for_client` | 已实现 |
| 共享 MCP 会话 | `backend/app/mcp/runtime/connection_tester.open_mcp_client_session` | 已实现 |
| 全屏 Modal UI | `frontend/src/features/agent/mcp/McpToolExplorerModal.tsx` | 已实现 |
| 操作列入口 | `frontend/src/features/agent/mcp/AgentMcpPage.tsx` | 已实现 |
| API 类型 | `frontend/src/api/mcp.ts` | 已实现 |
| Schema 表单辅助 | `frontend/src/features/agent/mcp/schemaFormUtils.ts` | 已实现 |
| 单元测试 | `backend/tests/test_mcp_client_explorer.py` | 已实现 |
