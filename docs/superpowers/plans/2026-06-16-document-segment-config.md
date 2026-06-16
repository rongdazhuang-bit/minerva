# 文档分段配置弹窗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善文档分段配置弹窗：展示完整只读索引/检索配置、按文档级 `process_rule` 加载与切换、支持「保存并处理」并触发重新索引。

**Architecture:** 扩展 `PATCH /documents/{id}` 接受 `process_rule`，后端新建 rule 行并 reprocess；前端 `DocumentSegmentConfigPanel` 复用向导面板，脏检查 + Popconfirm 保护文件切换。

**Tech Stack:** FastAPI, SQLAlchemy async, React, Ant Design, TanStack Query, pytest

**Spec:** `docs/superpowers/specs/2026-06-16-document-segment-config-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/app/dataset/api/schemas.py` | `DatasetDocumentPatchIn` 增加 `process_rule` |
| `backend/app/dataset/service/document_service.py` | `update_document` 保存 rule + `reprocess_document` |
| `backend/tests/test_document_segment_config.py` | 新建：PATCH process_rule 与 reprocess 测试 |
| `frontend/src/features/dataset/create/RetrievalSettingsPanel.tsx` | `retrievalLocked` prop |
| `frontend/src/features/dataset/api/documents.ts` | `patchDocument` body 类型扩展 |
| `frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx` | 主 UI 改造 |
| `frontend/src/i18n/locales/zh-CN.json` | 新文案 |
| `frontend/src/i18n/locales/en.json` | 新文案 |

---

### Task 1: 后端 — PATCH 文档 `process_rule` 测试

**Files:**
- Create: `backend/tests/test_document_segment_config.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for document-level process_rule patch and reprocess."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

# 复用 test_dataset_missing_apis 或 conftest 中的 client/fixture 模式
# 测试用例：
# 1. test_patch_document_process_rule_creates_new_rule_row
# 2. test_patch_document_process_rule_triggers_reindex
# 3. test_patch_archived_document_process_rule_rejected
# 4. test_patch_document_name_only_no_reprocess
```

具体实现时参考 `backend/tests/test_dataset_missing_apis.py` 的 dataset/document fixture 创建方式。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_document_segment_config.py -v
```

Expected: FAIL（`process_rule` 字段未实现或 reprocess 未触发）

---

### Task 2: 后端 — 实现 `reprocess_document` 与 PATCH 扩展

**Files:**
- Modify: `backend/app/dataset/api/schemas.py`
- Modify: `backend/app/dataset/service/document_service.py`

- [ ] **Step 1: 扩展 schema**

```python
class DatasetDocumentPatchIn(BaseModel):
    """Patch one document (rename or segment settings)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    process_rule: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> DatasetDocumentPatchIn:
        if self.name is None and self.process_rule is None:
            raise ValueError("name or process_rule required")
        return self
```

- [ ] **Step 2: 抽取 `reprocess_document`**

在 `document_service.py` 中从 `_reset_document_for_retry` 抽取公共逻辑：

```python
async def reprocess_document(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
) -> None:
    """Clear segments/vectors and re-enqueue indexing for one document."""
    await delete_vector_nodes_for_document(dataset, document.id)
    await delete_segments_for_document(session, document_id=document.id)
    document.indexing_status = INDEXING_STATUS_WAITING
    document.error = None
    document.is_paused = False
    document.processing_started_at = None
    document.parsing_completed_at = None
    document.cleaning_completed_at = None
    document.splitting_completed_at = None
    document.completed_at = None
    document.update_at = datetime.now(tz=UTC)
```

`_reset_document_for_retry` 改为调用 `reprocess_document`。

- [ ] **Step 3: 扩展 `update_document`**

```python
from app.dataset.domain.db.models import DatasetProcessRule
from app.dataset.service.chunk_service import serialize_process_rule

# 在 update_document 内：
if document.archived:
    raise AppError("dataset.document_archived", "已归档文档不可修改。", 422)

if "process_rule" in patch and patch["process_rule"] is not None:
    rule_payload = patch["process_rule"]
    process_row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=document.dataset_id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=document.created_by,  # 或从 patch 上下文传入 user_id
    )
    session.add(process_row)
    await session.flush()
    document.dataset_process_rule_id = process_row.id
    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    await reprocess_document(session, dataset=dataset, document=document)
    _enqueue_indexing(dataset.id, [document.id])
```

注意：`update_document` 需能获取 `user_id`（从 router 传入 `_member`）用于 `created_by`；若当前签名无 user_id，扩展 `update_document(..., user_id: uuid.UUID)` 并在 router 传入。

- [ ] **Step 4: 更新 router 传入 user_id**

`backend/app/dataset/api/router.py` 的 `patch_document` 将 `_member` 传给 service。

- [ ] **Step 5: 运行测试**

```bash
cd backend && pytest tests/test_document_segment_config.py -v
```

Expected: PASS

---

### Task 3: 前端 — `RetrievalSettingsPanel` 只读模式

**Files:**
- Modify: `frontend/src/features/dataset/create/RetrievalSettingsPanel.tsx`

- [ ] **Step 1: 新增 prop 并禁用交互**

```typescript
export type RetrievalSettingsPanelProps = {
  // ...existing
  /** When true, retrieval method cards and controls cannot be changed. */
  retrievalLocked?: boolean
}
```

在 `selectMethod`、卡片 `onClick`、`Switch`、`InputNumber`、`Slider`、`Select` 处判断 `retrievalLocked`（模式同 `IndexingMethodPanel.indexingLocked`）。

- [ ] **Step 2: 手动验证**

打开设置页确认检索面板仍可编辑（未传 `retrievalLocked`）。

---

### Task 4: 前端 — API 类型扩展

**Files:**
- Modify: `frontend/src/features/dataset/api/documents.ts`

- [ ] **Step 1: 扩展 `patchDocument`**

```typescript
export function patchDocument(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  body: { name?: string; process_rule?: Record<string, unknown> },
) {
  return apiJson<DatasetDocument>(base(workspaceId, datasetId, `/documents/${documentId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

确认 `DocumentListPage` 重命名调用 `patchDocument(..., { name })` 仍兼容。

---

### Task 5: 前端 — `DocumentSegmentConfigPanel` 改造

**Files:**
- Modify: `frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx`
- Modify: `frontend/src/features/dataset/documents/DocumentSegmentPanel.css`（保存按钮区域样式，如需）

- [ ] **Step 1: 扩展表单类型与检索数据加载**

```typescript
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import {
  parseRetrievalModelToForm,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'

type DocumentSegmentFormValues = ChunkingFormValues &
  IndexingFormValues &
  RetrievalFormValues
```

加载 dataset 时合并 `parseRetrievalModelToForm(dataset.retrieval_model ?? {})`。

- [ ] **Step 2: 分段规则仅来自文档**

```typescript
useEffect(() => {
  const document = documentQ.data
  const dataset = datasetQ.data
  if (!document || !dataset) return

  const savedRule = (document.process_rule ?? {}) as Record<string, unknown>
  // 不再 fallback dataset.process_rule
  form.setFieldsValue({
    doc_form: document.doc_form as DocumentSegmentFormValues['doc_form'],
    indexing_technique: (dataset.indexing_technique as ...) ?? 'high_quality',
    embedding_model_key: ...,
    ...parseProcessRuleToForm(savedRule),
    ...parseRetrievalModelToForm((dataset.retrieval_model ?? {}) as Record<string, unknown>),
  })
  setPreviewFileId(document.file_id ?? undefined)
  setPreviewState(null)
  setSavedSnapshot(serializeChunkingFields(form.getFieldsValue()))
}, [documentId, documentQ.data, datasetQ.data, form])
```

实现 `serializeChunkingFields`：从 form values 提取分段相关字段 JSON 字符串用于 dirty 比较。

- [ ] **Step 3: 脏检查与 Popconfirm 切换**

```typescript
const [savedSnapshot, setSavedSnapshot] = useState<string>('')

const isDirty = useMemo(() => {
  const current = serializeChunkingFields(form.getFieldsValue(true))
  return current !== savedSnapshot
}, [form, savedSnapshot, /* watch chunking fields via Form.useWatch or force update */])

const onPreviewFileIdChange = useCallback((fileId: string) => {
  const nextDocumentId = fileDocumentMap.get(fileId)
  if (!nextDocumentId || nextDocumentId === documentId) {
    setPreviewFileId(fileId)
    return
  }
  const switchDoc = () => {
    setPreviewFileId(fileId)
    setPreviewState(null)
    onDocumentChange(nextDocumentId)
  }
  if (isDirty) {
    // Ant Design Popconfirm 包裹切换逻辑，或 Modal.confirm — 项目约定用 Popconfirm
    // 在 Dropdown onClick 前拦截，使用 state 存 pendingDocumentId + Popconfirm open
  } else {
    switchDoc()
  }
}, [...])
```

实现方式：在 `ChunkPreviewPanel` 的 `onPreviewFileIdChange` 外包一层，或用 `pendingSwitch` state + 独立 Popconfirm 组件。

- [ ] **Step 4: 接入 `RetrievalSettingsPanel` 只读**

在 `IndexingMethodPanel` 下方、`ChunkingConfigSectionDivider` 后添加：

```tsx
<RetrievalSettingsPanel
  form={form as unknown as FormInstance<RetrievalFormValues>}
  rerankOptions={rerankOptions}
  modelsLoading={modelsQ.isLoading}
  vectorSearchDisabled={economyMode}
  retrievalLocked
/>
```

`economyMode` 来自 `Form.useWatch('indexing_technique')`。

- [ ] **Step 5: 移除顶部标题与设置页提示**

删除：

```tsx
<Typography.Title level={5} className="minerva-document-segment-panel__title">
  {t('dataset.documents.segmentConfig.title')}
</Typography.Title>
```

及 `indexingSettingsHint` 段落。

- [ ] **Step 6: 保存并处理**

```typescript
const saveM = useMutation({
  mutationFn: async () => {
    const values = await form.validateFields()
    const defaultRule = (documentQ.data?.process_rule ?? {}) as Record<string, unknown>
    const processRule = buildProcessRule(values, defaultRule)
    return patchDocument(workspaceId!, datasetId, documentId, { process_rule: processRule })
  },
  onSuccess: () => {
    message.success(t('dataset.documents.segmentConfig.saveOk'))
    setSavedSnapshot(serializeChunkingFields(form.getFieldsValue()))
    void queryClient.invalidateQueries({ queryKey: ['dataset-document', workspaceId, datasetId, documentId] })
    void queryClient.invalidateQueries({ queryKey: ['dataset-documents', workspaceId, datasetId] })
  },
})
```

底部添加：

```tsx
<div className="minerva-document-segment-panel__actions">
  <Button
    type="primary"
    loading={saveM.isPending}
    disabled={documentQ.data?.archived}
    onClick={() => saveM.mutate()}
  >
    {t('dataset.documents.segmentConfig.saveAndProcess')}
  </Button>
</div>
```

- [ ] **Step 7: 更新 `onResetChunking` / `onPreview`**

`defaultRule` 仅使用 `documentQ.data?.process_rule`，移除 dataset fallback。

---

### Task 6: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 添加/更新键**

```json
"dataset.documents.segmentConfig.saveAndProcess": "保存并处理",
"dataset.documents.segmentConfig.saveOk": "已保存，正在重新处理文档",
"dataset.documents.segmentConfig.unsavedConfirm": "有未保存的修改，是否放弃？",
"dataset.documents.segmentConfig.unsavedConfirmOk": "放弃",
"dataset.documents.segmentConfig.unsavedConfirmCancel": "继续编辑"
```

英文对应：

```json
"dataset.documents.segmentConfig.saveAndProcess": "Save & Process",
"dataset.documents.segmentConfig.saveOk": "Saved. Reprocessing document…",
"dataset.documents.segmentConfig.unsavedConfirm": "You have unsaved changes. Discard them?",
"dataset.documents.segmentConfig.unsavedConfirmOk": "Discard",
"dataset.documents.segmentConfig.unsavedConfirmCancel": "Keep editing"
```

可选：删除或保留未使用的 `segmentConfig.title`、`indexingSettingsHint`（若无引用可删）。

---

### Task 7: 验证

- [ ] **Step 1: 后端全量相关测试**

```bash
cd backend && pytest tests/test_document_segment_config.py tests/test_dataset_missing_apis.py -v
```

- [ ] **Step 2: 前端类型检查**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: 手工验收清单**

1. 文档列表 → 分段图标 → 无顶部「分段配置与预览」
2. 左侧四块配置，仅分段可编辑
3. 右侧默认显示当前文档文件
4. 切换另一文档 → 左侧分段参数变化
5. 修改分段未保存 → 切换文件 → Popconfirm
6. 保存并处理 → toast → 文档状态变 indexing

---

## Spec Coverage Checklist

| Spec 需求 | Task |
|-----------|------|
| 完整配置只读展示 | Task 3, 5 |
| 移除顶部标题 | Task 5 |
| 文件默认与切换加载 document process_rule | Task 5 |
| 保存并处理 + reprocess | Task 1, 2, 5 |
| 脏数据 Popconfirm | Task 5, 6 |
| archived 不可保存 | Task 2, 5 |

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-16-document-segment-config.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每任务派发新 subagent，任务间 review  
2. **Inline Execution** — 本会话按任务逐步执行，检查点 review

Which approach?
