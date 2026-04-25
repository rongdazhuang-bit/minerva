# OCR 工具管理（sys_ocr_tool + 管理端 UI）设计说明

**日期**：2026-04-24  
**状态**：已评审待实现  
**范围**：后端 CRUD（按 `app/tool/ocr` 分层）+ 管理端页面；数据源完全在服务端；运行时由调用方显式传入 `tool_id`，不在服务端定义全局/默认工具。

**数据模型决策（已确认）**：为 `sys_ocr_tool` 增加 **`workspace_id`**（FK → `workspaces`，`ON DELETE CASCADE`），按 workspace 隔离数据；不采用「全库共享同一批工具行、仅路径鉴权」的全局表方案。

---

## 1. 目标与成功标准

- **后端**：在当前 workspace 上下文中，对 OCR 工具配置进行列表、创建、读取、更新、删除；数据持久化于 `sys_ocr_tool`，且**按 `workspace_id` 隔离**。
- **前端**：OCR 设置/管理页仅通过 API 读写；移除对 `ocrSettingsStorage`（localStorage）的持久依赖，并提供可选的**一次性导入**以减轻升级摩擦。
- **成功标准**：已登录且属于路径中 `workspace_id` 的成员可完成 CRUD；非成员收到 403；不同 workspace 的数据互不可见；列表响应不暴露完整密钥（见第 5 节）；密钥不落日志。

---

## 2. 数据模型与迁移

### 2.1 表 `sys_ocr_tool`（目标形态）

在现有列（`id`, `name`, `url`, `auth_type`, `user_name`, `user_passwd`, `api_key`, `remark`, `create_at`, `update_at`）基础上**新增**：

| 列 | 类型 | 约束 |
|----|------|------|
| `workspace_id` | UUID | NOT NULL，FK → `workspaces(id)`，**ON DELETE CASCADE** |

索引建议：

- `ix_sys_ocr_tool_workspace_id`（`workspace_id`）

首版**不**强制 `(workspace_id, name)` 唯一，避免与历史数据冲突；若产品后续要求唯一，可再增迁移。

### 2.2 与 Alembic / `schema_postgresql.sql` 的关系

- 当前仓库中 `sys_ocr_tool` 出现在 `backend/sql/schema_postgresql.sql`，但 **Alembic 链中尚未包含该表**。
- **实现时**新增一条 Alembic revision（revises 当前 head：`c4f8a91b2d10`），在升级中定义**完整** `sys_ocr_tool`（含 `workspace_id`），与本文档及 ORM 一致。
- 同步更新 `schema_postgresql.sql`，使手工执行 SQL 的开发者与 Alembic 模型一致。
- **若某环境已用旧版 SQL 建过无 `workspace_id` 的表**：实现阶段需单独提供「`ALTER TABLE ... ADD COLUMN workspace_id` + 数据回填 + NOT NULL」的升级路径或运维说明；本 spec 以**新环境以 Alembic 为准**为默认前提。

### 2.3 ORM 与启动建表

- SQLAlchemy 模型放在 `backend/app/tool/ocr/domain/`（与 `.cursor/skills/code-comments/SKILL.md` 中 Minerva 工具模块范本一致）。
- 在 `app/infrastructure/db/bootstrap.py` 的 `_import_models()` 中注册该模型，保证 `AUTO_CREATE_TABLES=true` 时元数据完整。

---

## 3. 后端分层与路由注册

遵循 `.cursor/skills/code-comments/SKILL.md`（Minerva 工具模块章节）：

| 层级 | 职责 |
|------|------|
| `domain` | 实体、校验规则、领域错误码约定（不依赖 FastAPI） |
| `service` | 用例编排（CRUD） |
| `infrastructure` | 异步 Session 持久化实现 |
| `api` | FastAPI 路由、Pydantic、模块内 `deps` |

- 在 `app/api/router.py` 中 `include_router` 挂载本模块路由。
- **URL 前缀**：`/workspaces/{workspace_id}/ocr-tools`（若项目已有统一前缀如 `/api/v1`，实现时与现有 `health`/`auth` 风格对齐）。

### 3.1 鉴权

- 所有端点：`Depends(get_current_user)` + `Depends(require_workspace_member)`（路径参数 `workspace_id`）。
- 经需求澄清，**当前 workspace 内任意已登录成员**均可管理 OCR 工具（与仅校验 membership、不区分 owner/admin/member 的 `require_workspace_member` 一致）。

---

## 4. API 约定

假定基础路径为 `/workspaces/{workspace_id}/ocr-tools`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 当前 workspace 下工具列表 |
| POST | `/` | 创建 |
| GET | `/{id}` | 单条详情（含完整密钥字段，供编辑表单） |
| PATCH | `/{id}` | 部分更新 |
| DELETE | `/{id}` | 删除 |

**跨 workspace 访问**：若 `id` 存在但不属于该 `workspace_id`，返回 **404**（避免通过状态码推断其他租户资源是否存在）。

**`auth_type`**：Pydantic 层使用受控枚举或字面量集合，与列 `varchar(64)` 兼容；首版建议允许值：`none`、`basic`、`api_key`（实现可再与产品对齐命名，但与 DB 存字符串一致）。

**PATCH 与密钥**：约定「省略字段表示不修改；显式传 `null` 可表示清空（若业务需要）」或「空字符串表示不更新」——实现计划阶段择一写死，并在 OpenAPI/前端对齐。

---

## 5. 安全与隐私

- **`user_passwd`、`api_key` 不得写入应用日志。**
- **GET 列表**：响应中**不包含** `user_passwd`、`api_key` 的明文；可提供 `has_api_key`、`has_password` 等布尔字段便于 UI 展示「已配置」。
- **GET 单条**：返回完整字段，供编辑；传输层依赖 HTTPS（部署责任）。
- 注释规范见 `.cursor/skills/code-comments/SKILL.md`。

---

## 6. 管理端 UI

- 技术栈：现有 Ant Design、`apiJson`、`AuthContext.workspaceId`。
- 交互：表格（名称、URL、认证方式、备注、更新时间等）+ 新建/编辑（Modal 或 Drawer）+ 删除确认。
- **超时 `timeoutSec`**：原本地表单字段与「多工具 + 显式 tool_id」模型不完全对应；**首版**不在表结构增加 timeout，前端调用 OCR 时使用客户端默认（如 30s）或后续迭代再按「每工具扩展列」增加。
- **无服务端默认工具**：不在 UI 上强绑定「当前默认」；若需记住用户上次所选工具，仅用 **sessionStorage** 等纯前端状态，不写数据库。

### 6.1 本地配置迁移

- 检测到 `ocrSettingsStorage` 存在有效数据时，可提供「导入为一条工具」：将 `baseUrl` → `url`，`apiKey` → `api_key`，`auth_type` 按 `apiKey` 是否非空映射为 `api_key` 或 `none`；导入成功后**删除** localStorage 对应 key，避免双源。
- 若不做导入向导，则需在变更说明中提示用户手动重建；推荐实现可选导入以降低摩擦。

---

## 7. 测试与验收

- **后端**：pytest 异步测试（与项目现有习惯对齐）；至少覆盖：非成员 403、跨 workspace 404、CRUD 主路径、列表不含密钥明文。
- **手动验收**：两 workspace、两用户交叉验证隔离；浏览器网络面板确认列表响应无密钥。

---

## 8. 非目标（本 spec 之后）

- 实际发起 OCR 推理的 HTTP 客户端与 `tool_id` 解析（由调用链显式传入）。
- 密钥加密-at-rest（可后续用独立 spec 扩展）。

---

## 9. 自检记录（spec 定稿时核对）

- [x] 无未决 `TBD`：timeout 已明确首版不入库；PATCH 语义在实现计划中定死。
- [x] 与 `code-comments/SKILL.md` 中工具模块分层一致。
- [x] 权限模型与 `require_workspace_member` 一致。
- [x] 多租户隔离通过 `workspace_id` 落实。
