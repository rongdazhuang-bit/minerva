# 模型供应商 tags 与 Agent 对话选模过滤设计

> **Superseded（2026-05-29）:** 「保留 model_type」及 `CHAT` tag code 条款已由 `2026-05-29-model-type-to-tags-design.md` 替代。

**日期**：2026-05-28  
**状态**：已实现（2026-05-28）  
**范围**：在 `sys_models` 增加可多选的 `tags`（数据字典 `MODEL_TAG`）；设置页模型供应商 CRUD 支持维护 tags；Agent 对话页模型下拉与 Agent 后端跑图仅允许 tag 含 `CHAT` 的模型。翻译、规则、通用 `app/llm` 等其它选模/校验逻辑本期不变。

**关联文档**：

- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（模型供应商 CRUD 基线）
- `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`（`model_type` 与 `app/llm`；本期不修改其运行时规则）

---

## 1. 目标与成功标准

### 1.1 目标

- **数据**：`sys_models.tags` 存 `MODEL_TAG` 字典 code 的 JSON 数组；创建/更新时必填且至少一项；历史行迁移为 `["CHAT"]`。
- **管理端**：新增/编辑/查看/列表（含分组视图）展示并可编辑 tags（多选）。
- **Agent 对话**：模型下拉仅展示 `tags` 包含 `CHAT`、且满足现有可用性条件（`enabled`、有 `endpoint_url`、`has_api_key`）的模型。
- **Agent 后端**：使用 `model_id` 跑图时校验该行 `tags` 含 `CHAT`，否则 422（防前端绕过）。

### 1.2 成功标准

- owner/admin 可为模型配置多个 tag；非法 code 或空数组返回 422。
- 迁移后既有模型在 Agent 中仍可选（默认带 `CHAT`）。
- 未标 `CHAT` 的模型不出现在 Agent 下拉，且直接调用 Agent API 会被拒绝。
- 翻译页仍仅按 `model_type === 'translate'` 过滤；`app/llm` 仍按 `CHAT_MODEL_TYPES` / `EMBEDDING_MODEL_TYPES` / `RERANK_MODEL_TYPES` 校验 `model_type`。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| Tag 来源 | 数据字典 `MODEL_TAG`，落库存 **code** |
| 存储方案 | 方案 1：`sys_models.tags` JSONB 字符串数组 |
| tags 必填 | 是；历史数据默认 `["CHAT"]` |
| Agent 过滤 | `tags` 包含 `CHAT` |
| 后端 Agent | 强制校验 `CHAT` |
| 其它入口 | 规则不变（翻译仍用 `model_type` 等） |

---

## 2. 数据模型与迁移

### 2.1 列定义

| 列 | 类型 | 说明 |
|----|------|------|
| `tags` | `jsonb NOT NULL` | 字符串数组，元素为 `MODEL_TAG.code`；示例：`["CHAT"]`、`["CHAT","EMBEDDING"]` |

- **禁止** DB 外键；合法性由 service 校验（与 `model_type`、`provider_name` 一致）。
- ORM：`Mapped[list[str]]` 或 `list[str] | None` 映射 JSONB；读写前规范化（去空白、去重、保序可选为字典序或提交序，实现取**去重后按字典 code 排序**以稳定比较与展示）。

### 2.2 迁移步骤

1. Alembic revision：`ADD COLUMN tags jsonb`（可先 `nullable` + `server_default='["CHAT"]'::jsonb`）。
2. `UPDATE sys_models SET tags = '["CHAT"]'::jsonb WHERE tags IS NULL`（若存在空值）。
3. `ALTER COLUMN tags SET NOT NULL`（若第一步为 nullable）。
4. 同步 `backend/sql/schema_postgresql.sql` 与列注释。

### 2.3 常量

在 `backend/app/sys/model_provider/`（或 `app/llm/domain` 若需跨模块引用）定义：

```python
MODEL_TAG_DICT_CODE = "MODEL_TAG"
MODEL_TAG_CHAT = "CHAT"
```

Agent 与 model_provider 校验均引用 `MODEL_TAG_CHAT`，避免魔法字符串散落。

---

## 3. 数据字典 `MODEL_TAG`

### 3.1 约定

- 与 `MODEL_TYPE`、`MODEL_PROVIDER` 相同：按 **workspace** 维护字典；表单项选项来自 `listDictItems(MODEL_TAG)`。
- 落库与 API 传输均为字典项 **code**（如 `CHAT`）；列表/查看用 `DictText` 反查 **name** 展示。

### 3.2 首期字典项

| code | 建议显示名 | 本期用途 |
|------|------------|----------|
| `CHAT` | 对话（或「聊天」） | Agent 选模必选 tag |
| （可选预置） | `EMBEDDING`、`RERANK`、`TRANSLATE` 等 | 仅便于配置，**本期无额外过滤逻辑** |

### 3.3 环境准备

- 实现说明 / 运维 checklist：每个 workspace 须存在 `dict_code = MODEL_TAG` 且至少含 `CHAT` 项，否则创建模型时校验失败。
- 若有 workspace 种子或 demo 数据脚本，应插入 `MODEL_TAG` + `CHAT` 项（实现阶段对齐现有种子位置）。

---

## 4. 后端 API 与校验

### 4.1 Schema 变更

在 `ModelProviderCreateIn`、`ModelProviderPatchIn`、`ModelProviderListItemOut`、`ModelProviderDetailOut`、`ModelProviderGroupItemOut` 增加：

```python
tags: list[str]  # Create: min_length=1；Patch: 可选，传入时 min_length=1
```

Router 映射 `_to_list_item` / `_to_detail` / `_to_create_dict` / `_to_patch_dict` 需包含 `tags`。

### 4.2 Service 校验 `_validate_tags`

在 `model_provider_service` 中（与 `_validate_model_fields` 并列）：

1. `tags` 为非空 `list`。
2. 每项 `strip()` 后非空；**去重**。
3. 每项必须属于当前 workspace 字典 `MODEL_TAG` 的 code 集合（复用 `_load_dict_code_set(session, workspace_id, MODEL_TAG_DICT_CODE)`）。
4. 失败错误码建议：
   - 空或未传（create）：`model_provider.tags_required`（422）
   - 含非法 code：`model_provider.tag_invalid`（422）

Create 必须带 `tags`；Patch 若省略 `tags` 则不修改该字段。

### 4.3 Agent 后端校验

在 `ChatModelFactory.from_sys_model_row`（推荐，覆盖 `get` 与直接传 row 的路径）中，于 `enabled` / `endpoint` / `api_key` 校验之后增加：

```python
def _tags_include_chat(tags: object) -> bool:
    if not isinstance(tags, list):
        return False
    return MODEL_TAG_CHAT in {str(t).strip() for t in tags if t is not None}
```

- 不满足：`AppError("agent.model_tag_not_allowed", "该模型未标记为对话用途。", 422)`

**不改**：

- `app/llm/service/model_resolver.py` 的 `allowed_types`（仍按 `model_type`）。
- `translate` 前端 `model_type === 'translate'`。
- `rule` 等模块现有 `allowed_types`。

---

## 5. 前端：模型供应商页

### 5.1 表单

- 字段 `tags`：`Select mode="multiple"`，选项来自 `MODEL_TAG` 字典；**必填**（`rules: [{ required: true, message: ... }]`）。
- 遵循 minerva-ui 约定：其它 Select 可 `allowClear`；多选必填 tags 不使用 clear 清空到空（提交前校验至少一项）。
- `FormValues` / `detailToFormValues` / 提交 body 增加 `tags: string[]`。

### 5.2 列表与查看

- 分组表增加「标签」列：展示多个 tag（`DictText` 或 `Tag`）。
- 查看抽屉增加 tags 展示。

### 5.3 i18n

在 `zh-CN.json` / `en.json` 增加例如：

- `settings.modelProvidersFieldTags`
- `settings.modelProvidersFieldTagsRequired`
- `settings.modelProvidersColTags`

### 5.4 API 类型

`minerva-ui/src/api/modelProviders.ts` 各类型与 body 增加 `tags: string[]`。

---

## 6. 前端：Agent 对话页

### 6.1 下拉过滤

`AgentsPage` 中 `usableModels` 在现有 filter 上增加：

```ts
(Array.isArray(m.tags) ? m.tags : []).includes('CHAT')
```

（`listModelProviders` 返回的 list 项需含 `tags`。）

### 6.2 已选模型失效

- 若 `selectedModelId` 对应模型不再满足条件（含失去 `CHAT` tag），沿用现有 effect：在 `usableModels` 变化时回退到首个可用项或保持无选中（与当前 `enabled`/配置缺失行为一致）。

### 6.3 无可用模型

- 保持现有空态与禁用发送；无需新增独立文案（除非产品要求区分「无模型」与「无 CHAT 模型」——本期不做）。

---

## 7. 测试与验收

### 7.1 后端单测

| 用例 | 期望 |
|------|------|
| create 无 tags | 422 `tags_required` |
| tags 含非法 code | 422 `tag_invalid` |
| tags 合法多选 | 201/200 |
| Agent factory，tags 无 CHAT | 422 `agent.model_tag_not_allowed` |
| Agent factory，tags 含 CHAT | 通过（在 endpoint/api_key 等满足时） |

### 7.2 手动验收

1. 字典配置 `MODEL_TAG` + `CHAT`。
2. 创建仅 `EMBEDDING` tag 的模型 → Agent 下拉不可见；调 Agent 接口应 422。
3. 编辑模型加上 `CHAT` → Agent 可选。
4. 迁移环境旧模型默认可在 Agent 使用。

---

## 8. 非目标

- 不将翻译/规则/RAG/`app/llm` HTTP 改为按 `MODEL_TAG` 过滤（仍用 `model_type` 或现有规则）。
- 不新增 `GET /models?tag=CHAT` 专用查询参数（前端本地过滤即可；后续若有性能需求再加）。
- 不删除或弱化 `model_type` 字段与字典 `MODEL_TYPE`。
- 不为 `tags` 建 DB 级 CHECK / GIN 索引（本期数据量小；若日后按 tag 分页检索再评估）。

---

## 9. 实现对照（以代码为准，2026-05-28）

| 项 | 代码位置 | 备注 |
|----|----------|------|
| 常量 `MODEL_TAG` / `CHAT` | `backend/app/sys/model_provider/domain/constants.py` | |
| SQL 补丁 | `backend/sql/patches/2026-05-28-sys-models-tags.sql` | 现有库需手工执行 |
| ORM `tags` | `backend/app/sys/model_provider/domain/db/models.py` | JSONB，默认 `["CHAT"]` |
| `normalize_tags` | `backend/app/sys/model_provider/service/model_provider_service.py` | create/update |
| API | `backend/app/sys/model_provider/api/schemas.py`、`router.py` | |
| Agent 校验 | `backend/app/agent/infrastructure/chat_model_factory.py` | `agent.model_tag_not_allowed` |
| 单测 | `backend/tests/test_model_provider_tags.py`、`test_agent_chat_model_factory.py` | |
| 设置 UI | `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx` | 多选 + 列表列 |
| Agent 下拉 | `minerva-ui/src/features/agent/AgentsPage.tsx` | `tags.includes('CHAT')` |
| API 类型 | `minerva-ui/src/api/modelProviders.ts` | |
| i18n | `minerva-ui/src/i18n/locales/zh-CN.json`、`en.json` | |

---

## 10. 自检记录（定稿）

- [x] 无 `TODO` / `TBD` 占位。
- [x] 与 brainstorming 决策一致（方案 1、字典 `MODEL_TAG`、Agent 双端 `CHAT`、历史默认 `CHAT`）。
- [x] 无 DB 外键；tag 合法性在 service 层。
- [x] 与 `2026-05-28-llm-multi-capability-design` 边界清晰（不改 `app/llm` model_type 策略）。
- [x] 范围与非目标明确，可进入 `writing-plans` 实现计划。
