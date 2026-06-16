# 文档分段配置弹窗设计

**日期：** 2026-06-16  
**状态：** 已批准  
**范围：** 知识库 → 文档列表 → 操作列「分段」全屏弹窗（`DocumentSegmentConfigPanel`）

## 背景

用户从文档列表点击操作列分段图标进入全屏分段配置弹窗。当前实现仅展示分段配置（可编辑）与索引/Embedding（只读），缺少检索方式只读展示、顶部标题需移除、文件切换未严格按文档级 `process_rule` 加载，且无保存能力。

目标：与 Dify「Modify Chunk Settings」对齐——每文档独立分段规则、保存后自动重新处理。

## 需求摘要

| # | 需求 | 说明 |
|---|------|------|
| 1 | 完整配置展示 | 左侧展示：分段配置（可编辑）、索引方式、Embedding 模型、检索方式（后三者只读） |
| 2 | 移除顶部描述 | 删除「分段配置与预览」标题（`dataset.documents.segmentConfig.title`） |
| 3 | 文件选择与切换 | 右侧预览区文件下拉默认选中入口文档；切换时按 `dataset_document.dataset_process_rule_id` 加载该文档分段配置 |
| 4 | 保存 | 「保存并处理」按钮，文档级持久化 `process_rule`，保存后触发该文档重新索引 |
| 5 | 脏数据保护 | 切换文件时若有未保存修改，Popconfirm：「有未保存的修改，是否放弃？」 |

## 方案选择

采用 **方案 A**：扩展 `PATCH /datasets/{id}/documents/{doc_id}` 接受 `process_rule`，前端以单一 `activeDocumentId` 驱动表单与预览，复用创建向导/设置页面板组件。

未采用独立 POST 端点（方案 B）或预览/编辑文档解耦（方案 C），以降低改动面并与现有 `PATCH /datasets/{id}` 模式一致。

## 交互设计

### 入口与布局

- **入口：** `DocumentListPage` 操作列分段图标 → `DocumentSegmentModal`（`mode=config`）
- **布局：** `ChunkingConfigPreviewLayout` 左右分栏

| 区域 | 内容 | 可编辑 |
|------|------|--------|
| 左 | `SegmentationSettingsPanel` | ✅ |
| 左 | `IndexingMethodPanel`（`indexingLocked` + `embeddingReadOnly`） | ❌ |
| 左 | `RetrievalSettingsPanel`（`retrievalLocked`，新增 prop） | ❌ |
| 右 | `ChunkPreviewPanel`（文件下拉 + 分段预览） | 预览操作 |

### 文案

- 移除弹窗顶部 `Typography.Title`（「分段配置与预览」）
- 保留各 section 自带小标题
- 移除「要更改索引方式和 Embedding 模型，请前往设置」段落（索引/检索已完整只读展示）
- 底部主按钮文案：**保存并处理**（`dataset.documents.segmentConfig.saveAndProcess`）

### 文件切换

1. 打开弹窗时 `previewFileId = 入口文档.file_id`
2. 下拉列出同知识库所有有 `file_id` 的文档
3. 切换文件 → 解析对应 `documentId` → 若 `isDirty` 则 Popconfirm → 确认后 `onDocumentChange(documentId)`
4. 加载目标文档 `GET .../documents/{id}` 的 `process_rule`（经 `dataset_process_rule_id`）

### 脏状态

- 记录 `savedSnapshot`：分段相关表单字段的 JSON 序列化
- `isDirty` = 当前分段字段 ≠ `savedSnapshot`
- 切换文件、关闭弹窗前检查 `isDirty`

## 前端实现

### 主要文件

- `frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx` — 核心改造
- `frontend/src/features/dataset/documents/DocumentSegmentModal.tsx` — 无逻辑变更（已有 `activeDocumentId`）
- `frontend/src/features/dataset/create/RetrievalSettingsPanel.tsx` — 新增 `retrievalLocked`
- `frontend/src/features/dataset/api/documents.ts` — 扩展 `patchDocument` body
- `frontend/src/i18n/locales/zh-CN.json`、`en.json` — 文案

### 表单数据流

**分段字段来源（仅文档级）：**

```text
document.process_rule  ← load_document_process_rule(dataset_process_rule_id)
```

禁止回退到 `dataset.process_rule` 或 workspace 默认规则（避免多文档显示相同错误配置）。

**只读字段来源（知识库级）：**

```text
dataset.indexing_technique
dataset.embedding_model_provider + embedding_model
dataset.retrieval_model
```

### 保存流程

1. `form.validateFields()`（仅校验分段相关必填项）
2. `buildProcessRule(values, document.process_rule)` 构建 payload
3. `PATCH /datasets/{id}/documents/{doc_id}` body: `{ process_rule }`
4. 成功：toast、刷新 query、`savedSnapshot` 更新、`isDirty = false`
5. 文档列表已有 `indexing` 状态轮询自动反映处理进度

**两阶段实现（2026-06-16 修订）：** 后端先 commit 保存 `process_rule`，再 `reprocess` + 入队；阶段 2 失败时配置仍保留。详见 `2026-06-16-segment-save-then-reprocess-upload-cleanup-design.md`。

## 后端实现

### API 变更

扩展 `DatasetDocumentPatchIn`：

```python
class DatasetDocumentPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    process_rule: dict[str, Any] | None = None
```

校验：`name` 与 `process_rule` 至少提供一个（`exclude_unset=True`）。

### `update_document` 逻辑

当 `process_rule` 在 patch 中：

1. 文档存在且 `archived == False`，否则 422
2. 不修改 `doc_form`（chunk structure 创建后不可变，对齐 Dify）
3. 新建 `DatasetProcessRule` 行（同 `dataset_service.update_dataset` 的 rule 创建方式）
4. `document.dataset_process_rule_id = new_rule.id`
5. 调用 `reprocess_document`（从 `_reset_document_for_retry` 抽取共享逻辑）：
   - 删除向量节点、分段、子块
   - `indexing_status = waiting`，清空处理时间戳与 error
   - `_enqueue_indexing(dataset_id, [document_id])`
6. 任意非 archived 状态均可重新处理（不仅限于 `error`，对齐 Dify Save & Process）

### 响应

`get_document_detail` 继续通过 `load_document_process_rule` 返回 `process_rule`。

## 数据流

```text
列表点击文档 A
  → Modal(documentId=A)
  → GET document A → process_rule (via dataset_process_rule_id)
  → GET dataset → indexing/retrieval 只读
  → previewFileId = A.file_id

用户修改分段 → isDirty=true

切换文件 B
  → isDirty? → Popconfirm
  → documentId=B → GET B → 加载 B.process_rule

点击「保存并处理」
  → PATCH { process_rule }
  → 新建 rule + 更新 document + reprocess
  → isDirty=false
```

## 边界情况

| 场景 | 处理 |
|------|------|
| 文档无 `file_id` | 预览区提示无法预览；分段仍可保存并处理 |
| 文档 `archived` | 保存按钮禁用；API 返回 422 |
| 文档 `indexing` 中 | 允许保存；重新入队处理 |
| 多文档曾共享同一 `process_rule_id` | 保存仅为当前文档新建 rule，不影响其他文档 |
| `process_rule` 加载为 null | 禁止保存；展示错误或空状态提示 |
| 仅重命名 | 原有 `PATCH { name }` 行为不变，不触发 reprocess |

## 测试

### 后端

- `PATCH` 带 `process_rule`：新 `dataset_process_rule` 行、`dataset_process_rule_id` 更新
- 保存后 `indexing_status == waiting` 且 indexing 任务入队
- `archived` 文档保存 → 422
- 仅 `name` patch 不触发 reprocess

### 前端

- 四块配置展示，仅分段可交互
- 无顶部「分段配置与预览」
- 默认文件 = 入口文档
- 切换文件加载对应 `process_rule`
- 脏数据 Popconfirm
- 保存成功 toast

## 不在范围

- 修改知识库级索引/Embedding/检索（仍走设置页）
- 修改 `doc_form` / chunk structure
- 批量文档分段配置
- 文档列表分页超过 100 时的文件下拉完整加载（沿用现有 `page_size: 100`）

## 参考

- Dify：Modify Chunk Settings — 每文档独立 chunking settings；Save & Process 触发重新处理
- 现有：`DatasetSettingsPage`、`StepTwoChunking` 面板复用模式
- 数据模型：`docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md` §3 `dataset_process_rule`
