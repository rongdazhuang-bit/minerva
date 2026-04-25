# 模型供应商管理（sys_models + 管理端 UI）设计说明

**日期**：2026-04-25  
**状态**：已评审待实现  
**范围**：仅设置/管理端完成“模型供应商”页面 CRUD；存储统一落在 `sys_models`；页面按 `provider_name` 分组展示；本期不改对话/任务引擎读取逻辑，但为后续读取保留稳定边界。

---

## 1. 目标与成功标准

- **后端**：提供 `sys_models` 的列表、分组视图、创建、详情、更新、删除接口；按 `workspace_id` 严格隔离。
- **前端**：在 `ModelProvidersPage` 实现按供应商分组展示与模型行 CRUD，替换当前占位页面。
- **权限**：`owner/admin` 可增删改；`member` 只读。
- **字典约束**：
  - `provider_name` 取值来自字典 `MODEL_PROVIDER`。
  - `model_type` 取值来自字典 `MODEL_TYPE`。
  - 两个字段均落库存储字典 **name**（非 code）。
- **唯一性策略**：不增加唯一约束，允许重复记录；由后续业务消费阶段自行区分。
- **成功标准**：同一 workspace 内 owner/admin 可完整 CRUD，member 仅查看；跨 workspace 数据不可见；敏感字段不在列表中明文返回。

---

## 2. 数据模型与迁移

### 2.1 表 `sys_models`（目标形态）

沿用现有字段：`id`, `workspace_id`, `provider_name`, `model_name`, `model_type`, `enabled`, `load_balancing_enabled`, `auth_type`, `endpoint_url`, `api_key`, `auth_name`, `auth_passwd`, `context_size`, `max_tokens_to_sample`, `model_config`, `create_at`, `update_at`。

本期关键约束：

- 保留“无唯一约束”决策。
- 确保 `workspace_id` 隔离语义完整（含索引，且在 ORM/迁移/初始化 SQL 中一致）。
- 时间字段写入规则统一：创建写 `create_at`，更新写 `update_at`。

### 2.2 Alembic 与 `schema_postgresql.sql`

- 新增 Alembic revision，对 `sys_models` 的隔离约束与索引进行补齐/对齐（若环境已有偏差）。
- 同步更新 `backend/sql/schema_postgresql.sql`，保证手工初始化与迁移链一致。

> 注：如个别历史环境 `sys_models` 与当前目标形态不一致，实现阶段应提供可执行升级路径（例如补列/补索引/补外键），本 spec 不引入额外临时兼容表。

---

## 3. 后端模块化设计

### 3.1 目录结构

新增模块根目录：`backend/app/sys/model_provider/`，遵循与 OCR 工具一致的分层方式。

建议结构：

```text
app/sys/model_provider/
  __init__.py
  domain/
    __init__.py
    db/
      __init__.py
      models.py
  service/
    __init__.py
    model_provider_service.py
  infrastructure/
    __init__.py
    repository.py
  api/
    __init__.py
    deps.py
    router.py
    schemas.py
```

### 3.2 分层职责

- `domain`：ORM 实体、领域规则（不依赖 FastAPI）。
- `infrastructure`：数据库查询与持久化；不做视图聚合。
- `service`：业务编排、字典值合法性校验、分组组装、错误语义统一。
- `api`：路由、Pydantic 入出参、权限依赖装配。

### 3.3 路由与鉴权

- 在 `app/api/router.py` 注册模块路由。
- 所有接口都基于路径参数 `workspace_id`。
- 鉴权策略：
  - 读接口：workspace 成员可访问。
  - 写接口：仅 workspace 的 `owner/admin` 可访问；`member` 返回 403。

---

## 4. API 约定

基础前缀：`/workspaces/{workspace_id}/model-providers`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/models` | 平铺列表（管理与后续复用） |
| GET | `/grouped` | 按 `provider_name` 分组视图 |
| POST | `/models` | 创建模型行 |
| GET | `/models/{id}` | 读取详情 |
| PATCH | `/models/{id}` | 部分更新 |
| DELETE | `/models/{id}` | 删除 |

补充约定：

- 跨 workspace 访问一律返回 404（避免泄漏资源存在性）。
- 列表/分组接口不返回敏感字段明文（`api_key`、`auth_passwd`）。
- 详情接口可返回编辑所需字段；严禁记录敏感值日志。
- 由于 `provider_name`/`model_type` 落库存 `name`，返回体可附带反查的 `provider_code` / `model_type_code`（非持久化字段）作为后续引擎过渡辅助信息。

---

## 5. 字段规则与校验

### 5.1 基础字段

- `provider_name`：必填，必须命中字典 `MODEL_PROVIDER.name`。
- `model_name`：必填，长度不超过 128。
- `model_type`：必填，必须命中字典 `MODEL_TYPE.name`。
- `enabled`、`load_balancing_enabled`：布尔值。
- `endpoint_url`：可空；非空时需通过 URL 合法性校验。
- `context_size`、`max_tokens_to_sample`：可空；非空时为正整数。
- `model_config`：可空文本；首版不做 JSON Schema 强校验。

### 5.2 认证联动规则

`auth_type` 控制认证字段必填关系（命名与现有系统枚举保持一致）：

- `api_key`：`api_key` 必填，`auth_name`/`auth_passwd` 可空。
- `basic`：`auth_name` 与 `auth_passwd` 必填，`api_key` 可空。
- `none`：三者均可空。

字段组合不合法时返回 422。

---

## 6. 前端页面设计（Model Providers）

### 6.1 展示结构

- 页面主区域按 `provider_name` 分组展示（折叠面板或分组卡片）。
- 组标题展示供应商名称与模型数量。
- 组内使用表格展示模型行：`model_name`、`model_type`、`enabled`、`auth_type`、`endpoint_url`、更新时间、操作列。

### 6.2 交互动作

- 新增模型、编辑模型、删除模型、切换启用状态。
- “新增供应商”在交互上表现为“新增一条带新 `provider_name` 的模型记录”，不新增供应商主表。
- 删除后若某分组为空，前端移除该分组并刷新统计。

### 6.3 表单与字典

- `provider_name` 下拉：字典 `MODEL_PROVIDER`。
- `model_type` 下拉：字典 `MODEL_TYPE`。
- `auth_type` 切换时联动显示与必填规则。
- 文本输入与下拉遵循项目规范配置 `allowClear`。
- 数值字段使用 `InputNumber` 并限制最小值（正整数）。

### 6.4 权限呈现

- owner/admin：显示并可执行写操作按钮。
- member：页面仅可查看，写操作入口禁用或隐藏，并在必要处提示只读。
- 以后端权限校验结果为最终准则。

---

## 7. 测试与验收

### 7.1 后端测试（必做）

- workspace 隔离测试（A/B 工作区互不可见）。
- 角色权限测试（owner/admin 可写，member 写入 403、读取成功）。
- 字典合法性测试（`provider_name` 与 `model_type` 非法返回 422）。
- 认证联动校验测试（`auth_type` 与字段组合不符返回 422）。
- 分组接口测试（按 `provider_name` 聚合正确，组内记录完整）。

### 7.2 前端验收（建议）

- 分组渲染、分组计数、删除后分组更新正确。
- 表单联动与必填规则切换正确。
- member 视角仅只读。
- 字典加载失败时有清晰提示，不出现无反馈空白状态。

---

## 8. 非目标

- 本期不改对话/任务引擎读取 `sys_models` 的运行时逻辑。
- 本期不新增供应商主表。
- 本期不引入唯一约束。

---

## 9. 自检记录（定稿）

- [x] 无 `TODO` / `TBD` 占位。
- [x] 权限策略明确（owner/admin 写，member 只读）。
- [x] 字典映射与落库存储规则明确（存 name）。
- [x] 分组视图为“视图层语义”，不引入新增存储实体。
- [x] 范围与非目标边界清晰，可直接进入实现计划。
