# sys_models 字段重命名：max_tokens_to_sample → max_tokens

**日期**：2026-06-02  
**状态**：待实现  
**范围**：将 `sys_models.max_tokens_to_sample` 全量重命名为 `max_tokens`；同步更新 ORM、模型供应商 REST API、设置页 UI、Agent/规则/翻译运行时读取、测试及仓库内全部引用该字段名的文档。**不提供** `max_tokens_to_sample` 兼容别名。

**关联文档**：

- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（模型供应商 CRUD 基线；实现后字段名以本文为准）
- `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md`（Agent 列表 API 已对外使用 `max_tokens`；实现后与 DB 列名一致，移除映射层描述）

---

## 1. 目标与成功标准

### 1.1 目标

- **数据库**：列 `max_tokens_to_sample` 重命名为 `max_tokens`，数据与类型（`int2`、nullable）不变。
- **API**：`GET/POST/PATCH /model-providers/models` 及 grouped 子项 JSON 字段统一为 `max_tokens`。
- **运行时**：Agent `ChatModelFactory`、规则润色、翻译等从 `SysModel.max_tokens` 读取配置上限。
- **前端**：模型供应商表单与 `modelProviders.ts` 类型使用 `max_tokens`。
- **文档**：仓库内所有仍引用 `max_tokens_to_sample` 的 markdown 全局替换并修正过时「映射」表述。

### 1.2 成功标准

- SQL 补丁执行后，现有行的 token 上限数值不变。
- 设置页创建/编辑/查看模型时，请求与响应仅含 `max_tokens`。
- Agent 对话 run 仍支持：请求体 `max_tokens` 覆盖模型配置；未传时使用 `row.max_tokens`。
- 全仓 `rg max_tokens_to_sample` 无命中（代码与 docs）。
- 相关 pytest 通过。

### 1.3 需求决策摘要

| 项 | 决策 |
|----|------|
| 新列名 | `max_tokens` |
| API 兼容 | **无**（破坏性变更） |
| 文档 | **全局更新** |
| 迁移方式 | `RENAME COLUMN`（方案 1） |
| run 请求体 | 不变（已为 `max_tokens`） |

---

## 2. 数据库

### 2.1 补丁

文件：`backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql`

```sql
ALTER TABLE public.sys_models
  RENAME COLUMN max_tokens_to_sample TO max_tokens;

COMMENT ON COLUMN public.sys_models.max_tokens IS '最大 token 上限';
```

### 2.2 schema_postgresql.sql

- `CREATE TABLE sys_models` 中列名改为 `max_tokens`
- `COMMENT ON COLUMN public.sys_models.max_tokens` 与上一致

### 2.3 部署顺序

1. 在目标库执行补丁  
2. 同批或紧随其后部署后端 + 前端（避免旧客户端写 `max_tokens_to_sample`）

---

## 3. 后端

### 3.1 ORM

`backend/app/sys/model_provider/domain/db/models.py`：

```python
max_tokens: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
```

### 3.2 model_provider API

| 文件 | 变更 |
|------|------|
| `api/schemas.py` | `ModelProviderCreateIn` / `PatchIn` / `ListItemOut` / `DetailOut` / `GroupItemOut` 字段 `max_tokens_to_sample` → `max_tokens` |
| `api/router.py` | `_to_list_item` / `_to_group_item` / `_to_detail` / `_to_create_dict` 键名 |
| `service/model_provider_service.py` | `create_model` 写入 `max_tokens` |

校验规则不变：`ge=1`, `le=32767`，可空。

### 3.3 业务模块

| 模块 | 文件 | 变更 |
|------|------|------|
| Agent | `chat_model_factory.py` | `row.max_tokens_to_sample` → `row.max_tokens` |
| Agent | `api/v2/router.py` | `max_tokens=row.max_tokens`（去掉对旧列名的映射注释） |
| 规则 | `rule_base_service.py` | `model_row.max_tokens` |
| 翻译 | `translate_llm.py` | `row.max_tokens` |

**参数与列同名**：如 `ChatModelFactory.from_sys_model_row(..., max_tokens=None)` 保持现有逻辑——优先 run 参数，否则 `row.max_tokens`。

### 3.4 测试

更新字段名的文件（非穷举，实现时以 `rg max_tokens_to_sample` 为准）：

- `tests/test_agent_chat_model_factory.py`
- `tests/test_agent_conversation_models_api.py`
- `tests/test_llm_model_resolver.py`

---

## 4. 前端

### 4.1 API 类型

`minerva-ui/src/api/modelProviders.ts`：所有 `max_tokens_to_sample` → `max_tokens`。

### 4.2 设置页

`ModelProvidersPage.tsx`：

- 表单 `Form.Item name="max_tokens"`
- payload / diff / `formValuesFromDetail` 字段名
- 内部类型 `ModelFormValues`

`AgentsPage` 已使用 Agent API 的 `max_tokens`，**无需修改**。

### 4.3 i18n

| key | 变更 |
|-----|------|
| `settings.modelProvidersFieldMaxTokens`（en） | `"Max tokens"`（原 `"Max tokens to sample"`） |
| `settings.modelProvidersFieldMaxTokens`（zh-CN） | 保持「最大生成长度」 |

---

## 5. 文档全局更新

对仓库内 markdown（含 `docs/superpowers/specs/`、`docs/superpowers/plans/`、`docs/*.md`）：

1. `max_tokens_to_sample` → `max_tokens`
2. 修正 Agent 相关 spec 中「映射自 max_tokens_to_sample」为「读取 `sys_models.max_tokens`」

实现完成后对本文 **状态** 更新为「已实现（YYYY-MM-DD）」。

---

## 6. 非目标

- 不修改 `context_size`、`model_config` 等其它列。
- 不修改 LLM run / Agent run 请求体结构（已为 `max_tokens`）。
- 不保留 REST 或 ORM 层 alias / 双写字段。

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 旧前端写旧字段名导致 422 | 前后端同批发布 |
| 外部脚本仍用旧字段名 | 文档注明破坏性变更；全仓已无旧名 |

回滚：反向 `RENAME COLUMN max_tokens TO max_tokens_to_sample` + 回滚代码（需同批）。
