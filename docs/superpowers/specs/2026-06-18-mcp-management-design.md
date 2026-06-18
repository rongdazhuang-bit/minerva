# MCP 连接管理（工作区隔离 + Registry 门面）设计说明

**日期**：2026-06-18  
**状态**：已批准，待实现  
**范围**：在「智能体」菜单下新增 MCP 子菜单；按 workspace 管理 MCP 客户端（连接外部 MCP Server）与 MCP 服务端（Minerva 对外暴露）配置；环境变量开关；启动时加载运行时缓存；对话时按 workspace 动态注册 MCP 客户端工具。

**关系**：扩展 `docs/agent-module-design.md` 工具加载链路（`skill_loader.build_skill_react_agent`）；菜单体系见 `sys_menu` / `2026-06-10-menu-management-design.md`；CRUD 模式参考 `2026-04-24-ocr-tool-management-design.md`。

---

## 1. 目标与成功标准

### 1.1 目标

- 在智能体目录（`sub-agents`）下新增 **MCP** 子菜单（`order_num=4`，路径 `/app/agents/mcp`）。
- 工作区隔离管理两类配置：
  - **MCP 客户端**：Minerva Agent 作为 client 连接外部 MCP Server。
  - **MCP 服务端**：Minerva 对外暴露 MCP Server，暴露范围可配置。
- 环境变量分别控制客户端/服务端运行时是否启用。
- 服务启动时按开关从 DB 预热 `McpRuntimeRegistry` 内存缓存（**不**注入 Agent、**不**建立长连接）。
- Agent 对话 Run 开始时，按当前 `workspace_id` 动态连接已启用的 MCP 客户端并注册为 LangChain 工具。
- MCP 客户端 **创建/更新保存前必须通过连通性验证**（真实 handshake + list_tools）；失败禁止落库。
- CRUD 成功后 **立即** 刷新 Registry；无需重启服务。

### 1.2 成功标准

- owner/admin 可在 MCP 管理页完成客户端/服务端 CRUD；member 只读。
- 客户端保存前 test 失败时返回明确错误，DB 无变更。
- `MCP_CLIENT_ENABLED=true` 且 workspace 有 enabled 客户端时，Agent Run 可调用外部 MCP 工具（命名前缀 `mcp__{client}__{tool}`）。
- `MCP_SERVER_ENABLED=true` 时，外部 MCP client 可通过 `/mcp/s/{slug}/...` 访问配置范围内的工具。
- 删除被服务端引用的客户端返回 409；workspace 删除时应用层清理 MCP 相关行（无外键）。
- 角色菜单可收回 MCP 菜单可见性（`sys_role_menu`）。

### 1.3 非目标（本期）

- MCP 服务端保存时的运行时连通性探测（仅字段与引用校验）。
- 跨 workspace 共享 MCP 配置。
- MCP 连接池 / 全局长连接（按 Run 短连接）。
- MCP 工具在线调试 UI（已由 `2026-06-18-mcp-tool-explorer-design.md` 单独实现）。
- Git 同步或导入 Cursor `mcp.json` 一键迁移（可后续迭代）。

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| A. 单表 + role 字段 | `sys_mcp_config(role=client\|server)` + JSONB | 校验与 UI 分支过多 |
| B. 分表 | `sys_mcp_client` + `sys_mcp_server` | 结构清晰，采用 |
| **C. 分表 + Registry 门面** | B + `McpRuntimeRegistry` 统一缓存/刷新/Agent/路由 | **采用（最终方案）** |

架构：

```text
sys_mcp_client ──┐
                 ├──► McpRuntimeRegistry（门面）
sys_mcp_server ──┘         │
                           ├── warm on startup（按 env 开关）
                           ├── refresh on CRUD（立即）
                           ├── resolve_langchain_tools(ws) → Agent
                           └── mount_server_routes() → FastAPI
```

---

## 3. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `MCP_CLIENT_ENABLED` | `false` | 是否预热客户端缓存并在 Agent Run 中注册 MCP 工具 |
| `MCP_SERVER_ENABLED` | `false` | 是否挂载对外 MCP Server 路由 |
| `MCP_CONNECT_TIMEOUT` | `30` | 客户端连通性测试与 Run 内握手超时（秒） |

**约定**：新增/变更时同步 `backend/.env.example` 与 `backend/.env.dev`（Minerva 仓库约定）。

**启动流程**（`app/main.py` lifespan，在 `bootstrap_sys_menu_seed` 之后）：

1. 若 `MCP_CLIENT_ENABLED`：从 DB 加载全部 `enabled=true` 的 `sys_mcp_client` → `McpRuntimeRegistry.warm_clients()`。
2. 若 `MCP_SERVER_ENABLED`：加载 `sys_mcp_server` → `warm_servers()` + `mount_server_routes(app)`。
3. 不建立 MCP 长连接；不修改 Agent graph 编译逻辑。

---

## 4. 数据模型

> **Minerva 约定**：禁止外键；`workspace_id` 仅索引；删除与引用校验在 service 层实现。

### 4.1 `sys_mcp_client`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `workspace_id` | UUID, index | 工作区隔离 |
| `name` | VARCHAR(128) | 显示名（workspace 内唯一） |
| `transport` | VARCHAR(32) | `STDIO` / `SSE` / `STREAMABLE_HTTP` |
| `config` | JSONB | 非敏感连接配置 |
| `secrets` | JSONB | 敏感项（env、headers token 等） |
| `enabled` | BOOLEAN | 是否参与运行时 |
| `remark` | VARCHAR(256) | 可选 |
| `last_test_at` | TIMESTAMPTZ | 最近连通性测试时间 |
| `last_test_ok` | BOOLEAN | 最近测试结果 |
| `create_at` / `update_at` | TIMESTAMPTZ | |

**`config` 按 transport：**

| transport | config 字段 |
|-----------|-------------|
| `STDIO` | `command` (string), `args` (string[]), `cwd` (string, 可选) |
| `SSE` | `url` (string) |
| `STREAMABLE_HTTP` | `url` (string) |

**`secrets`：**

| transport | secrets 字段 |
|-----------|----------------|
| `STDIO` | `env` (object, 键值对) |
| `SSE` / `STREAMABLE_HTTP` | `headers` (object, 键值对) |

### 4.2 `sys_mcp_server`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `workspace_id` | UUID, index | |
| `name` | VARCHAR(128) | 显示名 |
| `slug` | VARCHAR(64) | URL 路径段，**全局唯一**，`^[a-z0-9][a-z0-9-]{1,62}$` |
| `enabled` | BOOLEAN | |
| `exposure` | JSONB | 暴露范围（见下） |
| `auth_type` | VARCHAR(32) | `NONE` / `BEARER` / `API_KEY` |
| `auth_secret` | VARCHAR(512) | 鉴权密钥（可空） |
| `remark` | VARCHAR(256) | |
| `create_at` / `update_at` | TIMESTAMPTZ | |

**`exposure` JSON 结构：**

```json
{
  "include_all_builtin": false,
  "builtin_skills": ["file", "weather"],
  "include_all_clients": false,
  "mcp_client_ids": ["uuid-1", "uuid-2"]
}
```

- `include_all_builtin=true`：暴露全部内置 Skills 工具（`skills/INDEX.json`）。
- `include_all_clients=true`：代理聚合该 workspace 全部 enabled 客户端 MCP 工具。
- 否则按 `builtin_skills` / `mcp_client_ids` 子集暴露。

### 4.3 删除策略（应用层）

| 操作 | 行为 |
|------|------|
| 删除 `sys_mcp_client` | 若被同 workspace 的 `sys_mcp_server.exposure.mcp_client_ids` 引用 → **409** `mcp.client_in_use` |
| 删除 workspace | service 层先删 `sys_mcp_client`、`sys_mcp_server`，再删 workspace（与现有 workspace 删除流程对齐） |

---

## 5. 后端模块

```text
backend/app/mcp/
├── __init__.py
├── domain/
│   └── db/
│       └── models.py          # SysMcpClient, SysMcpServer
├── infrastructure/
│   └── repository.py
├── service/
│   ├── mcp_client_service.py  # CRUD + test + 引用校验
│   └── mcp_server_service.py
├── runtime/
│   ├── registry.py            # McpRuntimeRegistry 门面
│   ├── connection_tester.py   # 保存前 handshake + list_tools
│   ├── client_bridge.py       # MCP SDK → LangChain Tool
│   └── server_router.py       # 对外 MCP 路由挂载
└── api/
    ├── router.py
    └── schemas.py
```

路由挂载：`app/core/api/router.py` 增加 `mcp` router。

**Python 依赖**：官方 `mcp` SDK（client + server）。

---

## 6. API

前缀：`/workspaces/{workspace_id}/mcp/`

### 6.1 MCP 客户端

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/clients` | member | 列表（secrets 脱敏） |
| GET | `/clients/{id}` | member | 详情 |
| POST | `/clients/test` | owner/admin | 连通性测试（不落库） |
| POST | `/clients` | owner/admin | 创建：内部先 test，通过才 persist + refresh |
| PATCH | `/clients/{id}` | owner/admin | 更新：同上 |
| DELETE | `/clients/{id}` | owner/admin | 删除 + refresh |

**保存强制流程：**

1. 校验字段与 transport 对应关系。
2. 调用 `McpConnectionTester.test(snapshot)`：handshake + `list_tools`。
3. 失败 → `422 mcp.client_connect_failed`（含 timeout / stdio stderr 摘要）。
4. 成功 → 写库，更新 `last_test_at` / `last_test_ok=true`，`McpRuntimeRegistry.refresh_workspace_clients(workspace_id)`。

**错误码：**

| code | HTTP | 场景 |
|------|------|------|
| `mcp.client_connect_failed` | 422 | test 或 save 内 test 失败 |
| `mcp.client_connect_timeout` | 422 | 超过 `MCP_CONNECT_TIMEOUT` |
| `mcp.client_stdio_failed` | 422 | stdio 进程启动失败 |
| `mcp.client_in_use` | 409 | 删除时被 server exposure 引用 |
| `mcp.client_name_duplicate` | 409 | 同 workspace 名称重复 |

### 6.2 MCP 服务端

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/servers` | member | 列表 |
| GET | `/servers/{id}` | member | 详情（auth_secret 脱敏） |
| POST | `/servers` | owner/admin | 创建 + refresh + remount |
| PATCH | `/servers/{id}` | owner/admin | 更新 + refresh + remount |
| DELETE | `/servers/{id}` | owner/admin | 删除 + unmount |

**保存校验（不测外部连通性）：**

- `slug` 全局唯一、格式合法。
- `exposure.builtin_skills` 每项存在于 `INDEX.json`。
- `exposure.mcp_client_ids` 每项属于同一 `workspace_id` 且 `enabled=true`。
- 保存后 `refresh_workspace_servers` + `mount_server_routes(app)`。

### 6.3 运行时状态

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/runtime-status` | member | 返回 `{ client_enabled, server_enabled }`（来自 Settings） |

### 6.4 对外 MCP 端点

- 路径：`/mcp/s/{slug}/...`（Streamable HTTP / SSE，按 MCP SDK 与 transport 规范）。
- 条件：`MCP_SERVER_ENABLED=true` 且对应 `sys_mcp_server.enabled=true`。
- 鉴权：`Authorization: Bearer <token>`（`BEARER`）或 `X-API-Key`（`API_KEY`）；`NONE` 不校验。

---

## 7. McpRuntimeRegistry 门面

```python
class McpRuntimeRegistry:
    _clients: dict[UUID, list[McpClientSnapshot]]
    _servers: dict[UUID, list[McpServerSnapshot]]

    async def warm_from_db(session) -> None
    def refresh_workspace_clients(workspace_id: UUID) -> None
    def refresh_workspace_servers(workspace_id: UUID) -> None
    def mount_server_routes(app: FastAPI) -> None

    async def resolve_langchain_tools(workspace_id: UUID) -> list[Tool]
    async def connect_client(snapshot: McpClientSnapshot) -> McpClientSession
```

**缓存刷新**：CRUD service 在 commit 成功后同步调用 refresh（方案 A，立即生效）。

**Agent 集成**（`skill_loader.build_skill_react_agent` 或 Run 初始化）：

```python
tools = load_tools_for_skill(skill_id, ctx)
if settings.mcp_client_enabled:
    mcp_tools = await mcp_registry.resolve_langchain_tools(ctx.workspace_id)
    tools = merge_tools_by_name(tools, mcp_tools)
```

- 工具命名：`mcp__{client_name}__{original_tool_name}`（`client_name` 规范化：小写、非字母数字 → `_`）。
- 按 **Run** 建立 MCP 连接，Run 结束关闭 session。
- 连接失败：记录日志 + SSE 事件 `mcp.tools_unavailable`；**不阻断**对话（内置 Skills 仍可用）。
- MCP 配置变更后，需失效 sub-agent 缓存 `(skill_id, workspace_id)`。

---

## 8. 前端

### 8.1 路由与菜单

| 项 | 值 |
|----|-----|
| 路由 | `/app/agents/mcp` |
| menu_key | `agents-mcp` |
| i18n | `nav.agentsMcp` |
| icon | `ApiOutlined` |
| order | 4（记忆之后） |

文件：

- `frontend/src/features/agent/mcp/AgentMcpPage.tsx`
- `frontend/src/features/agent/mcp/AgentMcpPage.css`
- `frontend/src/api/mcp.ts`
- 更新 `router.tsx`、`AppBreadcrumb.tsx`、i18n

菜单种子：`backend/sql/patches/2026-06-18-agents-mcp-menu.sql`；同步 `gen_sys_menu_seed_uuids.py`。

### 8.2 UI 布局

参考 `OcrSettingsPage`：Card + Tabs。

| Tab | 内容 |
|-----|------|
| MCP 客户端 | Table + Drawer；transport Select 切换字段 |
| MCP 服务端 | Table + Drawer；暴露范围多选 |

**客户端表单字段：**

- 公共：名称、启用、备注
- STDIO：command、args（Tag）、env（KV）、cwd
- SSE / Streamable HTTP：url、headers（KV）

**服务端表单字段：**

- 名称、slug、启用、鉴权类型/密钥、备注
- 暴露：Checkbox「全部内置 Skills」+ Skills 多选；Checkbox「全部客户端」+ 客户端多选

**保存逻辑（客户端）：**

1. 前端校验必填。
2. `POST .../clients/test`。
3. 通过后 `POST/PATCH`；失败展示错误，禁止提交。

**环境未启用提示：**

- `runtime-status.client_enabled=false` 时 Tab 顶栏 Alert：配置仅存储，对话不加载。
- `server_enabled=false` 时服务端 Tab 同理。

**二次确认**：删除使用 Ant Design `Popconfirm`（Minerva 约定）。

---

## 9. 权限

| 层级 | 规则 |
|------|------|
| 读 API | `require_workspace_member` |
| 写 API | `require_workspace_owner_or_admin`（与技能管理一致） |
| 菜单可见 | `sys_menu` + `sys_role_menu`；默认种子对管理员角色可见 |
| 收紧 | 管理员可通过角色管理收回 MCP 菜单 |

---

## 10. 错误处理摘要

| 场景 | 行为 |
|------|------|
| 客户端 test 超时 | `422 mcp.client_connect_timeout` |
| stdio 启动失败 | `422 mcp.client_stdio_failed` + stderr 摘要 |
| 对话时 MCP 连接失败 | 日志 + SSE `mcp.tools_unavailable`；对话继续 |
| `MCP_SERVER_ENABLED=false` | 配置可 CRUD；路由不挂载 |
| 删除被引用的 client | `409 mcp.client_in_use` |

---

## 11. 测试要点

- 客户端三种 transport 的 test + save  happy path。
- test 失败不落库。
- CRUD 后 Registry 立即反映（无需重启）。
- Agent Run 可调用 `mcp__*` 工具（`MCP_CLIENT_ENABLED=true`）。
- 外部 MCP client 访问 `/mcp/s/{slug}`（`MCP_SERVER_ENABLED=true`）。
- member 写接口 403；删除 Popconfirm 行为。
- workspace 删除清理 MCP 表。

---

## 12. 实现对照

| spec 条目 | 计划代码位置 | 状态 |
|-----------|--------------|------|
| sys_mcp_client / sys_mcp_server 表 | `backend/sql/patches/2026-06-18-sys-mcp-tables.sql` + ORM | 已实现 |
| McpRuntimeRegistry | `backend/app/mcp/runtime/registry.py` | 已实现 |
| MCP API | `backend/app/mcp/api/router.py` | 已实现 |
| Agent 工具合并 | `agent_graph_run_service.py` + `client_bridge.py` | 已实现 |
| 对外 Streamable HTTP + exposure 聚合 | `server_exposure.py` + `server_runtime.py` + `server_router.py` | 已实现 |
| 前端 MCP 页（编辑回填 / exposure 多选 / 权限） | `frontend/src/features/agent/mcp/AgentMcpPage.tsx` | 已实现 |
| 菜单种子 | `2026-06-18-agents-mcp-menu.sql` | 已实现 |
| 环境变量 | `app/config.py` | 已实现 |
| workspace 删除清理 MCP 表 | `tenant_service.delete_workspace` | 已实现 |
| SSE `mcp.tools_unavailable` | `agent/domain/sse_v2.py` + Run service | 已实现 |
| STDIO 连接超时 | `connection_tester.py` | 已实现 |

---

## 13. 决策记录

| 决策 | 选择 |
|------|------|
| 架构 | 方案 C：分表 + Registry 门面 |
| 客户端 transport | stdio + SSE + Streamable HTTP |
| 服务端暴露 | 可配置子集（builtin / clients / all flags） |
| 权限 | owner/admin 写 + 角色菜单可收紧 |
| 缓存刷新 | CRUD 后立即 refresh |
| 客户端保存 | 必须先通过连通性 test |
| 服务端保存 | 仅字段与引用校验，不测连通性 |
| Agent 连接失败 | 不阻断对话 |
