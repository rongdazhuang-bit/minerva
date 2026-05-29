# 移除 model_type，全链路改用 tags 设计

**日期**：2026-05-29  
**状态**：已定稿（brainstorming）  
**范围**：模型供应商 UI/API 删除 `model_type`；删除 `sys_models.model_type` 列；所有选模/校验从 `model_type` 相等改为 `tags` 包含（必要时排除）；`app/agent` 与 `app/llm` 各自实现 tag 校验，互不耦合。

**关联文档**：

- `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`（tags 引入；本期 supersede 其「保留 model_type」非目标）
- `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`（`app/llm` 能力模型；本期将 model_type 校验改为 tags）
- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（模型供应商 CRUD 基线）

---

## 1. 目标与成功标准

### 1.1 目标

- **数据**：删除 `sys_models.model_type` 列；删列前按映射将存量 `model_type` 写入 `tags`；`tags` 仍为 `MODEL_TAG` 字典 code 的 JSON 数组，创建/更新时必填且至少一项。
- **管理端**：模型供应商新增/编辑/查看/列表移除 `model_type` 字段；仅维护 `tags`（多选）。
- **运行时**：各业务模块按 `tags` 包含关系过滤模型；规则模块额外排除含 `TRANSLATE` 的模型。
- **模块边界**：`app/agent` 与 `app/llm` 各自实现 tag 校验逻辑，禁止互相 import 或共用 resolver。

### 1.2 成功标准

- owner/admin 创建/编辑模型时不再出现 `model_type`；`tags` 非法或空数组返回 422。
- 迁移后既有模型在各入口行为与映射一致（text 模型可用于 Agent/规则/chat；translate 仅翻译与 chat；embedding/rerank 仅对应端点）。
- Agent 后端与前端仅允许 `tags` 含 `TEXT` 的模型。
- `app/llm` chat 允许 `TEXT` 或 `TRANSLATE`；embeddings/rerank 分别要求 `EMBEDDINGS`/`RERANKING`。
- 规则润色仅允许含 `TEXT` 且不含 `TRANSLATE` 的模型。
- `MODEL_TYPE` 字典不再被代码引用（不迁移、不清理历史字典数据）。

### 1.3 需求决策摘要

| 项 | 决策 |
|----|------|
| UI/API | 删除 `model_type` 字段 |
| DB | 删除 `sys_models.model_type` 列 |
| 字典 | 不迁移 `MODEL_TYPE`；仅使用 `MODEL_TAG` |
| 校验架构 | 统一 tag 语义；`app/agent` 与 `app/llm` 独立实现 |
| 规则模块 | `tags` 含 `TEXT` 且不含 `TRANSLATE` |
| 错误码（llm） | `ai.model_type_mismatch` → `ai.model_tag_mismatch` |

### 1.4 model_type → tag 映射

| 原 `model_type` | 新 tag code |
|-----------------|-------------|
| `text` | `TEXT` |
| `translate` | `TRANSLATE` |
| `embedding` | `EMBEDDINGS` |
| `rerank` | `RERANKING` |

---

## 2. 各模块过滤规则

| 模块 | 过滤条件 | 实现位置 |
|------|----------|----------|
| Agent 对话（前端下拉） | `tags` 含 `TEXT` | `minerva-ui/.../AgentsPage.tsx` |
| Agent 后端跑图 | `tags` 含 `TEXT` | `app/agent/infrastructure/chat_model_factory.py` |
| `app/llm` chat | `tags` 含 `TEXT` 或 `TRANSLATE` | `app/llm/service/model_resolver.py` |
| 翻译 | `tags` 含 `TRANSLATE` | `translate_llm` → `llm_service` |
| `/embeddings` | `tags` 含 `EMBEDDINGS` | `app/llm/service/model_resolver.py` |
| `/rerank` | `tags` 含 `RERANKING` | `app/llm/service/model_resolver.py` |
| 规则润色 | `tags` 含 `TEXT` 且不含 `TRANSLATE` | `rule_base_service` → `llm_service` |

---

## 3. 模块边界与依赖

```
model_provider (SysModel.tags, MODEL_TAG 常量, CRUD normalize_tags)
       │
       ├── app/agent ── ChatModelFactory + 本地 _tags_allow_agent()
       │                 （禁止 import app/llm）
       │
       └── app/llm ──── model_resolver + 本地 _tags_match()
                         （禁止 import app/agent）
              │
              ├── translate_llm → llm_service
              └── rule_base_service → llm_service
```

**允许共享**：

- `model_provider/domain/constants.py`：tag code 字符串常量（`TEXT`、`TRANSLATE`、`EMBEDDINGS`、`RERANKING`）及 `MODEL_TAG_DICT_CODE`。
- `SysModel.tags` ORM 字段与 `model_provider_service.normalize_tags`。

**禁止**：

- `app/agent` ↔ `app/llm` 任意 import。
- 跨 agent/llm 的共享 resolver 或共享 tag 校验模块（逻辑可相同，代码各自维护）。

---

## 4. 数据模型与迁移

### 4.1 删列前数据迁移

补丁文件：`backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql`

```sql
-- 以 model_type 为准覆写 tags（修正此前默认 ["CHAT"] 等与类型不符的行）
UPDATE public.sys_models SET tags = CASE model_type
  WHEN 'text' THEN '["TEXT"]'::jsonb
  WHEN 'translate' THEN '["TRANSLATE"]'::jsonb
  WHEN 'embedding' THEN '["EMBEDDINGS"]'::jsonb
  WHEN 'rerank' THEN '["RERANKING"]'::jsonb
  ELSE tags
END;

ALTER TABLE public.sys_models DROP COLUMN IF EXISTS model_type;
```

同步更新 `backend/sql/schema_postgresql.sql`；ORM `SysModel` 移除 `model_type` 映射。

### 4.2 MODEL_TAG 字典

工作区字典 `MODEL_TAG` 须包含以下 code（显示名实现阶段对齐 i18n/种子）：

| code | 用途 |
|------|------|
| `TEXT` | Agent、规则（非翻译）、chat 文本 |
| `TRANSLATE` | 翻译、chat（翻译类模型） |
| `EMBEDDINGS` | `/embeddings` |
| `RERANKING` | `/rerank` |

废弃此前 spec 中的 `CHAT`、`EMBEDDING`、`RERANK` code（迁移脚本已覆写存量 tags）。

### 4.3 model_provider 常量

`backend/app/sys/model_provider/domain/constants.py`：

```python
MODEL_TAG_DICT_CODE = "MODEL_TAG"
MODEL_TAG_TEXT = "TEXT"
MODEL_TAG_TRANSLATE = "TRANSLATE"
MODEL_TAG_EMBEDDINGS = "EMBEDDINGS"
MODEL_TAG_RERANKING = "RERANKING"
```

移除 `MODEL_TAG_CHAT`。

---

## 5. 后端：model_provider

### 5.1 API Schema / Router

从 `ModelProviderCreateIn`、`ModelProviderPatchIn`、`ModelProviderListItemOut`、`ModelProviderDetailOut`、`ModelProviderGroupItemOut` 及 router 映射中**移除** `model_type`。

### 5.2 Service

- 移除 `_validate_model_fields` 中对 `MODEL_TYPE` 字典的校验及 `model_type` 写入。
- 保留 `normalize_tags`（`MODEL_TAG` 字典、非空、去重排序）。

---

## 6. 后端：app/agent（独立实现）

### 6.1 校验

在 `chat_model_factory.py`（或 `app/agent/domain/model_tags.py`）：

```python
def _tags_allow_agent(tags: object) -> bool:
    if not isinstance(tags, list):
        return False
    return MODEL_TAG_TEXT in {str(t).strip() for t in tags if t is not None}
```

- 不满足：`AppError("agent.model_tag_not_allowed", "该模型未标记为对话用途。", 422)`（文案可微调为「文本对话」；错误码保持不变）。

### 6.2 约束

- 不调用 `app.llm.service.model_resolver`。
- 单测：`backend/tests/test_agent_chat_model_factory.py` 改用 `TEXT` tag。

---

## 7. 后端：app/llm（独立实现）

### 7.1 常量（定义在 app/llm/domain，不 export 给 agent）

```python
CHAT_MODEL_TAGS = frozenset({"TEXT", "TRANSLATE"})
EMBEDDING_MODEL_TAGS = frozenset({"EMBEDDINGS"})
RERANK_MODEL_TAGS = frozenset({"RERANKING"})
```

（字符串值与 `model_provider` 常量一致，但 **不在 agent 侧 import**；llm 模块内可字面量或复制常量名。）

### 7.2 model_resolver

```python
async def resolve_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    allowed_tags: frozenset[str],
    excluded_tags: frozenset[str] | None = None,
) -> ResolvedModel:
```

本地 helper `_tags_match(tags, allowed_tags, excluded_tags)`：

1. 解析 `tags` 为 strip 后的 set。
2. `tag_set & allowed_tags` 非空。
3. 若 `excluded_tags` 非空，`tag_set & excluded_tags` 为空。
4. 失败：`AppError("ai.model_tag_mismatch", f"模型标签不支持当前调用。", 422)`。

### 7.3 ResolvedModel

移除 `model_type` 字段（策略层仅使用 `model_name`、`endpoint_url`、`api_key`）。

### 7.4 llm_service / router

- `allowed_types` 参数更名为 `allowed_tags`（及可选 `excluded_tags`）。
- chat 默认 `CHAT_MODEL_TAGS`；embeddings/rerank 各用对应集合。
- `translate_llm`：`TRANSLATE_MODEL_TAGS = frozenset({"TRANSLATE"})`；`_assert_translate_dict` 改为检查 `MODEL_TAG` 字典含 `TRANSLATE`（不再检查 `MODEL_TYPE`）。
- `rule_base_service`：`allowed_tags=frozenset({"TEXT"})`, `excluded_tags=frozenset({"TRANSLATE"})`。

### 7.5 约束

- 不 import `app.agent`。
- 单测：`test_llm_model_resolver.py`、`test_llm_domain_models.py` 等更新 tag 语义与错误码。

---

## 8. 前端

### 8.1 模型供应商页

- 删除 `model_type` 表单项、列表列、查看抽屉、`MODEL_TYPE` 字典加载及相关 i18n。
- 新建默认 tags：字典存在 `TEXT` 时默认 `["TEXT"]`（替代原 `CHAT` 默认逻辑）。
- 保留 tags 多选（必填）。

### 8.2 Agent 页

`usableModels` 过滤：`tags.includes('TEXT')`（替换 `CHAT`）。

### 8.3 翻译页

`tags.includes('TRANSLATE')`（替换 `model_type === 'translate'`）。

### 8.4 API 类型

`minerva-ui/src/api/modelProviders.ts`：各类型移除 `model_type`。

---

## 9. 测试与验收

### 9.1 后端单测

| 用例 | 期望 |
|------|------|
| create/patch 仍含 model_type 字段 | schema 不再接受（或忽略）；无 model_type 必填 |
| Agent factory，tags 无 TEXT | 422 `agent.model_tag_not_allowed` |
| resolve_model，tags 无 allowed 交集 | 422 `ai.model_tag_mismatch` |
| resolve_model，含 excluded tag | 422 `ai.model_tag_mismatch` |
| rule：TEXT only 通过；TEXT+TRANSLATE 拒绝 | 422 |
| chat：TEXT 或 TRANSLATE 通过 | OK |

### 9.2 手动验收

1. 执行 SQL 补丁，确认 `model_type` 列已删除，tags 与映射一致。
2. 设置页无「模型类型」字段；tags 多选正常。
3. Agent / 翻译 / 规则 / AI 三端点选模与 422 行为符合 §2 表。
4. 环境 `MODEL_TAG` 字典含 TEXT/TRANSLATE/EMBEDDINGS/RERANKING。

### 9.3 文档

- 更新 `docs/ai-api.md`（model_type → tags、错误码）。
- 在 `2026-05-28-model-provider-tags-design.md` 文首注明已被本期 supersede 的条款。

---

## 10. 非目标

- 不迁移或清理工作区历史 `MODEL_TYPE` 字典数据。
- 不新增 `GET /models?tag=` 查询参数。
- 不为 `tags` 建 GIN 索引。
- 不在 agent/llm 之间抽取共享 resolver 包。

---

## 11. 自检记录（定稿）

- [x] 无 `TODO` / `TBD` 占位。
- [x] model_type → tag 映射与过滤规则无歧义。
- [x] agent/llm 解耦边界明确。
- [x] 无 DB 外键；tag 合法性在 model_provider service。
- [x] 迁移脚本以 model_type 覆写 tags，再删列。
- [x] 范围与非目标明确，可进入 `writing-plans`。
