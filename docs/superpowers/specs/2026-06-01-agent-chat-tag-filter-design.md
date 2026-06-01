# Agent 对话选模：CHAT tag 与专用模型列表接口设计

**日期**：2026-06-01  
**状态**：已实现（2026-06-01）  
**范围**：智能体对话页模型下拉改为仅展示 Agent 可用模型；新增 `GET /agent/v2/models` 专用接口（SQL 一次过滤）；Agent 跑图校验 `tags` 含 `CHAT`；`MODEL_TAG` 字典新增 `CHAT` 项。**不**修改 `/model-providers/models`、规则、`app/llm` 的 tag 规则；**不**自动给存量模型写入 `CHAT`。

**关联文档**：

- `docs/superpowers/specs/2026-05-29-model-type-to-tags-design.md`（当前 Agent 使用 `TEXT`；本期 Agent 改为 `CHAT`，其它模块仍用 `TEXT` 等）
- `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`（tags 引入与 Agent 早期 `CHAT` 设想）
- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（模型供应商 CRUD 基线）

---

## 1. 目标与成功标准

### 1.1 目标

- **Agent 选模 tag**：仅 `tags` 数组含 **`CHAT`** 的模型可用于智能体对话（可与 `TRANSLATE`、`EMBEDDINGS` 等 tag 共存）。
- **专用列表 API**：`GET /workspaces/{workspace_id}/agent/v2/models`，在 SQL 层过滤可用模型，前端不再本地过滤 tag / enabled / endpoint / api_key。
- **跑图防绕过**：`ChatModelFactory` 校验 `CHAT` tag（422 `agent.model_tag_not_allowed`）。
- **字典**：各工作区 `MODEL_TAG` 字典 idempotent 插入 `CHAT` 项，供管理员手动勾选。
- **响应字段**：对外暴露 `max_tokens`（映射自 `sys_models.max_tokens_to_sample`），与 run 请求体字段名一致。

### 1.2 成功标准

- 管理员在模型供应商中为模型勾选 `CHAT` 后，该模型出现在 Agent 下拉（且满足 enabled、endpoint、api_key 条件）。
- 仅含 `TEXT`、未含 `CHAT` 的模型不出现在 Agent 下拉；直接 run 含非 `CHAT` 的 `model_id` 返回 422。
- 列表按 **模型提供商名称 → 模型名称** 升序排列。
- 规则、`app/llm` chat、翻译、embeddings、rerank 行为与现网一致（仍用 `TEXT` / `TRANSLATE` / `EMBEDDINGS` / `RERANKING`）。
- 设置页 `/model-providers/models` 与 `/grouped` 不变。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| Agent 选模 tag | **`CHAT`**（非 `TEXT`） |
| 范围 | **仅 Agent 对话** |
| 存量模型 tags | **不自动迁移**；管理员手动勾选 `CHAT` |
| 多 tag 共存 | **允许**（含 `CHAT` 即可，不排斥其它 tag） |
| 列表接口 | **独立** `GET /agent/v2/models`（不改通用 `/models?tags=`） |
| 过滤位置 | **SQL WHERE**（tag + enabled + endpoint + api_key） |
| 排序 | `provider_name ASC`, `model_name ASC`, `id ASC` |
| 响应 max tokens 字段 | **`max_tokens`** ← `max_tokens_to_sample` |
| 字典 | SQL 补丁插入 `CHAT` 字典项；不改 `sys_models.tags` 存量 |

---

## 2. API 设计

### 2.1 端点

| 项 | 值 |
|----|-----|
| 方法 / 路径 | `GET /workspaces/{workspace_id}/agent/v2/models` |
| Router | `backend/app/agent/api/v2/router.py` |
| 权限 | `require_workspace_member`（与会话列表一致） |
| 响应 | `list[AgentConversationModelOut]` |

### 2.2 响应 Schema

```python
class AgentConversationModelOut(BaseModel):
    id: uuid.UUID
    provider_name: str
    model_name: str
    endpoint_url: str          # SQL 过滤后必非空
    max_tokens: int | None     # 来自 sys_models.max_tokens_to_sample
    tags: list[str]
```

- 不返回 `api_key`；不返回 `max_tokens_to_sample` 字段名。
- `has_api_key` 省略（SQL 已保证有 key）。

### 2.3 不变更的端点

- `GET /workspaces/{id}/model-providers/models`
- `GET /workspaces/{id}/model-providers/grouped`

---

## 3. SQL 过滤与排序

### 3.1 Repository 方法

在 `backend/app/sys/model_provider/infrastructure/repository.py` 新增：

```python
async def list_agent_conversation_models(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysModel]:
    ...
```

由 `agent/api/v2/router.py` 调用；**不在** `app/agent` 内 duplicate SQL。

### 3.2 WHERE 条件

| 条件 | SQL / ORM |
|------|-----------|
| 工作区 | `workspace_id = :workspace_id` |
| tags 含 CHAT | `tags @> '["CHAT"]'::jsonb`（常量 `MODEL_TAG_CHAT`） |
| 已启用 | `enabled = true` |
| 有接入地址 | `endpoint_url IS NOT NULL AND btrim(endpoint_url) <> ''` |
| 有 API Key | `api_key IS NOT NULL AND btrim(api_key) <> ''` |

SQLAlchemy 示例：`SysModel.tags.contains([MODEL_TAG_CHAT])` 配合 `func.btrim` 与非空判断。

### 3.3 ORDER BY

```text
provider_name ASC, model_name ASC, id ASC
```

---

## 4. Agent 后端跑图（防绕过）

### 4.1 常量

`backend/app/sys/model_provider/domain/constants.py` 新增：

```python
MODEL_TAG_CHAT = "CHAT"
```

保留 `MODEL_TAG_TEXT` 等现有常量。

### 4.2 ChatModelFactory

`backend/app/agent/infrastructure/chat_model_factory.py`：

```python
def _tags_allow_agent(tags: object) -> bool:
    if not isinstance(tags, list):
        return False
    return MODEL_TAG_CHAT in {str(t).strip() for t in tags if t is not None}
```

- 错误码：`agent.model_tag_not_allowed`（文案可微调为「未标记为 Agent 对话用途」）。
- 仍校验 workspace、enabled、endpoint、api_key（与列表语义一致）。
- **禁止** import `app.llm`。

---

## 5. 字典补丁（非模型 tags 迁移）

### 5.1 补丁文件

`backend/sql/patches/2026-06-01-model-tag-chat-dict-item.sql`

- 对每个 workspace 的 `MODEL_TAG` 字典，**若不存在** code=`CHAT` 的项则插入（显示名建议「对话」，`item_sort` 与现有项协调）。
- **不** `UPDATE sys_models SET tags = ...`。

### 5.2 管理员操作

1. 确认工作区字典有 `CHAT` 项（补丁或手动维护）。
2. 在「模型供应商」编辑模型，勾选 `CHAT` tag，并配置 endpoint / API Key / 启用。

---

## 6. 前端

### 6.1 API 客户端

`minerva-ui/src/api/agent.ts` 新增：

```typescript
export type AgentConversationModel = {
  id: string
  provider_name: string
  model_name: string
  endpoint_url: string
  max_tokens: number | null
  tags: string[]
}

export function listAgentConversationModels(workspaceId: string) {
  return apiJson<AgentConversationModel[]>(
    `/workspaces/${workspaceId}/agent/v2/models`,
  )
}
```

### 6.2 AgentsPage

- `useQuery` 改调 `listAgentConversationModels`。
- `usableModels` 直接使用 API 返回数组（删除 `includes('TEXT')` 及 enabled / endpoint / `has_api_key` 本地过滤）。
- run 时使用 `modelRow.max_tokens`（不再读 `max_tokens_to_sample`）。
- Select `options` label 仍为 `` `${provider_name} · ${model_name}` ``。

### 6.3 空状态 i18n

更新 `agents.noModelsConfiguredHint`（中/英）：除 endpoint / API Key / 启用外，说明需为模型勾选 **`CHAT`** tag，并链到模型供应商设置。

---

## 7. 模块边界

```text
model_provider (SysModel, MODEL_TAG_* 常量, repository.list_agent_conversation_models)
       │
       └── app/agent ── GET /agent/v2/models
                       ChatModelFactory._tags_allow_agent() → CHAT
                       （禁止 import app/llm）

app/llm / 规则 / 翻译 ── 仍用 TEXT、TRANSLATE 等（不变）
```

---

## 8. 测试

| 层级 | 用例 |
|------|------|
| Repository | 仅 CHAT 无 key → 排除；有 key 无 CHAT → 排除；disabled → 排除；全满足 → 命中；排序 provider → model |
| API | GET `/agent/v2/models` 结构与过滤一致；无 secret 泄漏 |
| ChatModelFactory | 无 CHAT → 422；CHAT + EMBEDDINGS → 通过 |
| 回归 | `app/llm` / 规则 tag 测试不受影响 |

---

## 9. 非目标

- 不给存量 `sys_models.tags` 自动追加 `CHAT`。
- 不改 `/model-providers/models` 查询参数或语义。
- 不将 Agent 与 `app/llm` 的 tag 校验合并为共享模块。
- 不修改模型供应商新建默认值（仍为 `TEXT`，不含 `CHAT`）。

---

## 10. 实现后文档回填

实现完成并验证通过后，将本文 **状态** 更新为「已实现（YYYY-MM-DD）」。
