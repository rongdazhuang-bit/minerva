# 规则库「配置 → 模型配置」（`rule_config_model`）设计说明

**日期**：2026-04-28  
**状态**：已确认，待实现  
**范围**：在 **`backend/app/rule`** 内实现表 **`public.rule_config_model`** 的 CRUD 与 **`model_id` → `sys_models.id`** 的引用校验；抽取 **工程 / 专业 / 文档类型** 三元组共用能力（**方案 B**），供 **`rule_base`** 与 **`rule_config_model`** 共用；前端在 **`minerva-ui/src/features/rules`** 新增独立页面，替换当前 **`/app/rules/config/models`** 误用的 `ModelProvidersPage`；定义运行时按上下文 **解析配置** 的优先级，**未命中则报错**（不静默回退默认模型）。

---

## 1. 目标与成功标准

- **数据**：业务唯一键 **`(workspace_id, engineering_code, subject_code, document_type)`**；三列语义与规则列表一致（字典级联 **`RULE_ENG_SUBJECT_DOC`**，未选维度存 **`NULL`**）；**列 `upate_at` 更名为 `update_at`**，并与 `create_at` 由服务端统一维护。
- **后端**：在 `workspace_id` 成员上下文中，提供分页列表、创建、详情、部分更新、物理删除；列表筛选参数与 **`rule_base`** 列表对齐（可选 `engineering_code` / `subject_code` / `document_type`）；写入时校验 **`model_id`** 对应行存在且 **`sys_models.workspace_id`** 与路径参数一致。
- **共用模块（方案 B）**：将三元组的 **规范化**（strip、空串→`NULL`）与 **列表筛选条件构造**（SQLAlchemy）抽到 **`app/rule`** 下单一明确模块；**`rule_base` 仓储/服务改为调用该模块**，避免两处规则漂移。
- **前端**：新页面沿用 `RulesManagementPage` 的级联筛选与表格/表单交互模式；**`model_id`** 通过同工作空间 **`sys_models`** 已有列表接口填充下拉；分页默认 **10**（`DEFAULT_PAGE_SIZE`）。
- **运行时解析（供后续校审/流水线使用）**：给定上下文三元组 `(e, s, d)`，按 **从具体到笼统** 顺序解析唯一配置行；**若四档均未命中，视为错误**（调用方返回明确业务错误，**不**回退设置页默认模型）。
- **删除模型策略**：本 spec **不** 单独规定「删除 `sys_models`」时与 `rule_config_model` 的 **ON DELETE** 语义；实现阶段若增加外键，与现有 **`model_provider`** 删除行为对齐即可，不在此文档展开产品策略。

**成功标准**：成员可完成模型配置 CRUD；违反唯一键返回可预期的冲突错误；非法或跨 workspace 的 `model_id` 被拒绝；前端路由与面包屑与「规则库 → 配置 → 模型配置」一致；**`schema_postgresql.sql` 与 Alembic 迁移链对齐**。

---

## 2. 数据模型与迁移

### 2.1 表 `public.rule_config_model`（目标形态）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | uuid PK | 新建由服务端生成 |
| `workspace_id` | uuid NOT NULL | 工作空间隔离 |
| `model_id` | uuid NOT NULL | 引用 **`sys_models.id`**（同 workspace） |
| `engineering_code` | varchar(64) NULL | 工程编码，与规则列表一致 |
| `subject_code` | varchar(64) NULL | 专业 |
| `document_type` | varchar(64) NULL | 文档类型 |
| `sys_prompt` | varchar(1024) NULL | 系统提示词 |
| `user_prompt` | text NULL | 用户提示词 |
| `chat_memory` | text NULL | 对话记忆 |
| `create_at` / `update_at` | timestamptz | 服务端维护；**实现时将历史列名 `upate_at` 迁移为 `update_at`** |

### 2.2 约束与索引

- **`workspace_id` → `public.workspaces(id) ON DELETE CASCADE`**（与 `rule_base` / `sys_models` 一致）。
- **`model_id` → `public.sys_models(id)`**：实现阶段添加外键以保证引用完整；**ON DELETE** 行为按上节「删除模型策略」——本 spec 不强制二选一，与现有模型管理模块保持一致即可。
- **业务唯一性**：`(workspace_id, engineering_code, subject_code, document_type)`。  
  PostgreSQL 默认 UNIQUE 对 **NULL** 的处理可能导致「多行全 NULL」并存；实现时 **必须** 采用以下之一并在迁移中写死：  
  - **PostgreSQL 15+**：`UNIQUE NULLS NOT DISTINCT` 涵盖四列；或  
  - **表达式唯一索引**：对四列使用统一空值哨兵（例如 `coalesce(col, '')`），与规则侧 **空串不入库、只存 NULL** 的约定兼容。  
  具体以部署目标 PG 版本为准，在实现计划中选定一种并全环境统一。
- **列表性能**：保留 `(workspace_id)` 上的 btree 索引（若唯一索引已覆盖可合并评估）。

### 2.3 主键约束命名

- 将现有误名 **`rule_base_config_pk`** 更正为与表名一致的命名（如 **`rule_config_model_pkey`**），与 `schema_postgresql.sql`、Alembic 同步。

---

## 3. 共用模块（工程 / 专业 / 文档）

### 3.1 后端位置与职责

建议在 **`app/rule/domain/`** 下新增独立模块（单文件或子包均可），例如 **`scope_triple.py`**（名称实现阶段可微调，职责如下）：

1. **`normalize_scope_triple(engineering_code, subject_code, document_type)`**  
   输入为 API 层字符串或 `None`；**strip** 后 **空串视为 `None`**；输出为 `tuple[str | None, str | None, str | None]`。  
   **`rule_base` 与 `rule_config_model` 的写入、列表 query 解析均经此函数**。

2. **`scope_triple_filter_conditions(model_class, workspace_id, e, s, d)`**  
   `model_class` 为带有 `workspace_id` 与三列 code 的 ORM 类；返回 SQLAlchemy 可用条件列表（与当前 `rule_base` 的 `_list_filters` 语义一致：**仅对非 `None` 的维度追加等值条件**）。

3. **（可选）唯一键冲突前校验**：创建/更新前在 service 层用相同规范化后的三元组查询是否已存在他行，便于返回 **409** 与明确文案（数据库唯一约束仍作为最终防线）。

**重构要求**：`backend/app/rule/infrastructure/repository.py`（或当前 `rule_base` 查询所在模块）中现有 `_list_filters` 逻辑 **迁移为调用上述共用函数**，避免重复实现。

### 3.2 前端共用

将 **`RULE_ENG_SUBJECT_DOC`** 级联相关的 **路径 ⇄ 三元组** 转换、列表 query 构造，从 `RulesManagementPage.tsx` **抽取**到 **`features/rules`** 下独立模块（例如 `scopeTriple.ts`），由 **规则列表页** 与 **模型配置页** 共同引用，保证与后端规范化规则一致（首段非空才形成路径等现有行为保持不变）。

---

## 4. 后端 API（`app/rule`）

### 4.1 路由前缀

建议资源路径：**`/workspaces/{workspace_id}/rule-config/models`**（kebab-case，与 `rule-base` 并列），或实现计划中与此等价、全局唯一的单数/复数约定。**不得**与 `rule-base` 路径混用同一 collection。

### 4.2 鉴权与分页

- 与现有规则接口一致：`get_current_user` + `require_workspace_member`。
- 列表：`page` / `page_size`，默认 **`DEFAULT_PAGE_SIZE`**，上限 **100**。

### 4.3 端点草图

| 方法 | 路径 | 行为 |
|------|------|------|
| `GET` | `.../rule-config/models` | 分页列表；可选 `engineering_code`、`subject_code`、`document_type`（经共用规范化） |
| `POST` | 同上 | 创建；校验 `model_id` 归属当前 workspace；三元组经规范化后插入 |
| `GET` | `.../rule-config/models/{id}` | 详情；跨 workspace **404** |
| `PATCH` | 同上 | 部分更新；若修改三元组则再次校验唯一键 |
| `DELETE` | 同上 | 物理删除 |

### 4.4 响应与关联展示

- 列表/详情可在同一查询中 **join** `sys_models` 的展示字段（如 `provider_name`、`model_name`），减少前端二次请求（可选但推荐）。

### 4.5 错误语义

- 不存在或非本 workspace：**404**。  
- 违反唯一键：**409**（或项目统一冲突码）。  
- `model_id` 无效或非本 workspace：**400** 或 **422**，与全局错误体一致。  
- **运行时解析未命中**（见下节）：由调用方（如未来校审服务）转为 **明确业务错误**（例如专用异常或 **422**），**禁止**静默使用默认模型。

---

## 5. 运行时配置解析（非 HTTP，供业务调用）

**输入**：`workspace_id`，以及上下文 **`(e, s, d)`**（已与 `rule_base` 行或文档解析结果对齐并经 **同一套 normalize**）。

**解析顺序**（在相同 `workspace_id` 下，按序查找 **第一条存在** 的行）：

1. `(e, s, d)`  
2. `(e, s, NULL)`  
3. `(e, NULL, NULL)`  
4. `(NULL, NULL, NULL)`

若 **四档均为未命中**：**报错**（由调用方映射为对用户/日志可读信息）；**不**回退设置页或其它默认模型配置。

**实现建议**：在 **`app/rule/service`** 中提供纯函数 **`resolve_rule_config_model(session, workspace_id, e, s, d) -> RuleConfigModel`**，并附 **单元测试**；本迭代 HTTP CRUD 可不依赖该函数，但 spec 要求该行为与数据模型一并落地，避免后续校审接入时再议。

---

## 6. 前端

### 6.1 路由与组件

- **`/app/rules/config/models`** 挂载 **新组件**（如 `RulesModelConfigPage`），**移除**对 `ModelProvidersPage` 的引用。
- **设置 → 模型供应商**（`/app/settings/models`）仍为 `sys_models` CRUD，职责不变。

### 6.2 页面行为

- 筛选条：与 `RulesManagementPage` 相同的 **字典级联**（`RULE_ENG_SUBJECT_DOC`）。  
- 表格：展示三元组（优先字典 **名称**）、关联模型展示名、`sys_prompt` 可截断、时间列、操作列。  
- 表单：`model_id` **Select**，选项来自 **`sys_models` 列表接口**（仅当前 workspace）；长文本 **TextArea**；与项目表单规范一致（如 **`allowClear`** 适用于适用控件）。

### 6.3 i18n

- 复用/补充 `nav.rulesConfig`、`nav.rulesModelConfig` 及表单字段文案（`en.json` / `zh-CN.json`）。

---

## 7. 测试与验收

- **后端**：唯一键冲突；非法 `model_id`；列表筛选与 `rule_base` 行为一致；**`resolve_rule_config_model`** 四档顺序及未命中抛错。  
- **前端**：路由与面包屑正确；与设置页模型列表互不干扰。  
- **数据库**：Alembic 升级与 `schema_postgresql.sql` 手工初始化结果一致。

---

## 8. 与现有文档的关系

- **`2026-04-27-rule-base-crud-design.md`** 中包路径已演进为 **`app/rule`**；本 spec 以当前仓库 **`backend/app/rule`** 为准。  
- **`sys_models`** 行为仍以 **`2026-04-25-model-providers-management-design.md`** 为参考；本功能仅 **引用** 模型主数据，不修改其权限模型 unless 冲突时在实现计划中显式说明。

---

## Spec 自检（2026-04-28）

- **占位符**：已消除；PG 唯一实现二选一在 §2.2 明确由实现计划按版本定稿。  
- **一致性**：未命中报错、方案 B 共用模块、`update_at` 更名与 user 决策一致。  
- **范围**：单 spec 可支撑一个实现计划；运行时解析以函数+测试为界，不接具体 LLM。  
- **歧义**：「删除模型策略」明确为 **本 spec 不展开**；外键 ON DELETE 与 `model_provider` 对齐即可。
