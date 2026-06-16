# 添加文档分段配置与完成页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将「添加文档」向导改为 3 步（上传 → 分段配置预览 → 完整完成页），并在 append API 支持 `process_rule`，为每个新文档创建独立的 `DatasetProcessRule` 行。

**Architecture:** 扩展 `POST /datasets/{id}/documents` 接受可选 `process_rule`；前端 append 模式复用创建向导面板与 `DocumentSegmentConfigPanel` 的只读索引/检索模式；完成页用 `completionVariant` 区分创建与添加文档文案。

**Tech Stack:** FastAPI, SQLAlchemy async, React, Ant Design, TanStack Query, pytest

**Spec:** `docs/superpowers/specs/2026-06-16-document-append-chunking-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/app/dataset/api/schemas.py` | `DatasetDocumentAppendIn` 增加 `process_rule` |
| `backend/app/dataset/service/document_service.py` | `append_documents` 每文档独立 rule 行 |
| `backend/app/dataset/api/router.py` | 传递 `process_rule` 给 service |
| `backend/tests/test_document_append_chunking.py` | append + process_rule 单元测试 |
| `frontend/src/features/dataset/api/documents.ts` | `appendDocuments` body 类型扩展 |
| `frontend/src/features/dataset/create/AppendChunkingStep.tsx` | append Step 1 UI（新建） |
| `frontend/src/features/dataset/create/DatasetCreateWizard.tsx` | append 3 步流程 |
| `frontend/src/features/dataset/create/StepThreeProcessing.tsx` | `completionVariant` 替代 `isAppend` 精简布局 |
| `frontend/src/i18n/locales/zh-CN.json` | append 完成页文案 |
| `frontend/src/i18n/locales/en.json` | append 完成页文案 |

---

### Task 1: 后端 — append `process_rule` 测试

**Files:**
- Create: `backend/tests/test_document_append_chunking.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for append documents with per-document process_rule rows."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.domain.constants import INDEXING_STATUS_WAITING
from app.dataset.service import document_service


def _dataset_stub(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "chunk_structure": "text_model",
    }
    defaults.update(overrides)
    return type("DatasetStub", (), defaults)()


def _upload_stub(upload_id: uuid.UUID, workspace_id: uuid.UUID, name: str = "demo.txt"):
    return type(
        "UploadStub",
        (),
        {"id": upload_id, "workspace_id": workspace_id, "name": name},
    )()


@pytest.mark.asyncio
async def test_append_with_process_rule_creates_rule_per_document(monkeypatch) -> None:
    """Each appended document gets its own DatasetProcessRule row."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    file_id_a = uuid.uuid4()
    file_id_b = uuid.uuid4()
    dataset = _dataset_stub(id=dataset_id)
    added: list = []

    session.add = MagicMock(side_effect=lambda row: added.append(row))

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_max_pos(*args, **kwargs):
        _ = args, kwargs
        return 0

    uploads = {
        file_id_a: _upload_stub(file_id_a, workspace_id, "a.txt"),
        file_id_b: _upload_stub(file_id_b, workspace_id, "b.txt"),
    }

    async def fake_get_upload(session_obj, upload_id):
        _ = session_obj
        return uploads.get(upload_id)

    session.get = AsyncMock(side_effect=fake_get_upload)

    enqueue_ids: list[uuid.UUID] = []

    def fake_enqueue(ds_id, doc_ids):
        _ = ds_id
        enqueue_ids.extend(doc_ids)

    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service.repo, "count_documents_for_dataset", fake_count)
    monkeypatch.setattr(document_service.repo, "max_document_position", fake_max_pos)
    monkeypatch.setattr(document_service, "_enqueue_indexing", fake_enqueue)

    process_rule = {
        "mode": "custom",
        "rules": {"segmentation": {"delimiter": "\n\n", "max_length": 800}},
    }

    result = await document_service.append_documents(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dataset_id,
        file_ids=[file_id_a, file_id_b],
        process_rule=process_rule,
    )

    rule_rows = [row for row in added if row.__class__.__name__ == "DatasetProcessRule"]
    doc_rows = [row for row in added if row.__class__.__name__ == "DatasetDocument"]

    assert len(rule_rows) == 2
    assert len(doc_rows) == 2
    assert rule_rows[0].id != rule_rows[1].id
    assert doc_rows[0].dataset_process_rule_id == rule_rows[0].id
    assert doc_rows[1].dataset_process_rule_id == rule_rows[1].id
    assert doc_rows[0].dataset_process_rule_id != doc_rows[1].dataset_process_rule_id
    assert doc_rows[0].indexing_status == INDEXING_STATUS_WAITING
    assert doc_rows[1].indexing_status == INDEXING_STATUS_WAITING
    assert len(enqueue_ids) == 2
    assert len(result["documents"]) == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_without_process_rule_uses_latest_rule(monkeypatch) -> None:
    """Omitting process_rule keeps existing latest-rule behavior."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    file_id = uuid.uuid4()
    dataset = _dataset_stub(id=dataset_id)
    latest_rule = type("RuleStub", (), {"id": uuid.uuid4()})()
    added: list = []

    session.add = MagicMock(side_effect=lambda row: added.append(row))

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_max_pos(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_latest(*args, **kwargs):
        _ = args, kwargs
        return latest_rule

    session.get = AsyncMock(return_value=_upload_stub(file_id, workspace_id))

    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service.repo, "count_documents_for_dataset", fake_count)
    monkeypatch.setattr(document_service.repo, "max_document_position", fake_max_pos)
    monkeypatch.setattr(document_service.repo, "get_latest_process_rule", fake_latest)
    monkeypatch.setattr(document_service, "_enqueue_indexing", lambda *_: None)

    await document_service.append_documents(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dataset_id,
        file_ids=[file_id],
        process_rule=None,
    )

    rule_rows = [row for row in added if row.__class__.__name__ == "DatasetProcessRule"]
    doc_rows = [row for row in added if row.__class__.__name__ == "DatasetDocument"]
    assert len(rule_rows) == 0
    assert len(doc_rows) == 1
    assert doc_rows[0].dataset_process_rule_id == latest_rule.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_document_append_chunking.py -v`

Expected: FAIL — `append_documents()` got unexpected keyword argument `process_rule`

---

### Task 2: 后端 — 实现 append `process_rule`

**Files:**
- Modify: `backend/app/dataset/api/schemas.py`
- Modify: `backend/app/dataset/service/document_service.py`
- Modify: `backend/app/dataset/api/router.py`

- [ ] **Step 1: 扩展 schema**

在 `backend/app/dataset/api/schemas.py` 的 `DatasetDocumentAppendIn` 中增加：

```python
class DatasetDocumentAppendIn(BaseModel):
    """Append documents to an existing knowledge base."""

    file_ids: list[uuid.UUID] = Field(min_length=1)
    process_rule: dict[str, Any] | None = None
```

- [ ] **Step 2: 扩展 `append_documents` 签名与循环逻辑**

在 `backend/app/dataset/service/document_service.py`：

```python
async def append_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    dataset_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    process_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append uploaded files to an existing dataset and enqueue indexing."""

    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    if not file_ids:
        raise AppError("dataset.file_ids_required", "请至少选择一个文件。", 422)
    existing_count = await repo.count_documents_for_dataset(session, dataset_id=dataset.id)
    if existing_count + len(file_ids) > settings.dataset_max_files_per_dataset:
        raise AppError("dataset.too_many_files", "文件数量超过知识库上限。", 422)

    shared_rule = None
    if process_rule is None:
        shared_rule = await repo.get_latest_process_rule(session, dataset_id=dataset.id)
        if shared_rule is None:
            raise AppError("dataset.process_rule_missing", "知识库缺少分段规则。", 422)

    max_position = await repo.max_document_position(session, dataset_id=dataset.id)
    batch = uuid.uuid4().hex
    documents: list[DatasetDocument] = []
    for offset, upload_id in enumerate(file_ids, start=1):
        upload = await session.get(DatasetUploadFile, upload_id)
        if upload is None or upload.workspace_id != workspace_id:
            raise AppError("dataset.upload_not_found", "上传文件不存在。", 404)

        if process_rule is not None:
            rule_row = DatasetProcessRule(
                id=uuid.uuid4(),
                dataset_id=dataset.id,
                mode=str(process_rule.get("mode") or "custom"),
                rules=serialize_process_rule(process_rule),
                created_by=user_id,
            )
            session.add(rule_row)
            await session.flush()
            rule_id = rule_row.id
        else:
            rule_id = shared_rule.id  # type: ignore[union-attr]

        doc = DatasetDocument(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset.id,
            position=max_position + offset,
            data_source_type=DATA_SOURCE_UPLOAD_FILE,
            data_source_info=json.dumps({"upload_file_id": str(upload_id)}),
            dataset_process_rule_id=rule_id,
            batch=batch,
            name=upload.name,
            created_from="web",
            created_by=user_id,
            file_id=str(upload_id),
            indexing_status=INDEXING_STATUS_WAITING,
            doc_form=dataset.chunk_structure or "text_model",
        )
        session.add(doc)
        documents.append(doc)
    await session.commit()
    for doc in documents:
        await session.refresh(doc)
    task_id = _enqueue_indexing(dataset.id, [doc.id for doc in documents])
    return {
        "batch": batch,
        "documents": [_document_to_dict(doc) for doc in documents],
        "indexing_task_id": task_id,
    }
```

- [ ] **Step 3: router 传参**

在 `backend/app/dataset/api/router.py` 的 `append_documents` handler：

```python
result = await document_svc.append_documents(
    session,
    workspace_id=workspace_id,
    user_id=user.id,
    dataset_id=dataset_id,
    file_ids=body.file_ids,
    process_rule=body.process_rule,
)
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && pytest tests/test_document_append_chunking.py -v`

Expected: PASS（2 tests）

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataset/api/schemas.py backend/app/dataset/service/document_service.py backend/app/dataset/api/router.py backend/tests/test_document_append_chunking.py
git commit -m "feat(dataset): append documents with per-document process_rule"
```

---

### Task 3: 前端 API — `appendDocuments` 扩展

**Files:**
- Modify: `frontend/src/features/dataset/api/documents.ts`

- [ ] **Step 1: 扩展函数签名**

```typescript
/** Append uploaded files to an existing knowledge base. */
export function appendDocuments(
  workspaceId: string,
  datasetId: string,
  payload: { file_ids: string[]; process_rule?: Record<string, unknown> },
) {
  return apiJson<{ batch: string; documents: DatasetDocument[]; indexing_task_id: string | null }>(
    base(workspaceId, datasetId, '/documents'),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}
```

- [ ] **Step 2: 更新 `DatasetCreateWizard.tsx` 中的调用处**（Task 5 会改，此处先确保类型编译通过）

将：

```typescript
appendDocuments(workspaceId, datasetId, uploads.map((item) => item.id))
```

改为：

```typescript
appendDocuments(workspaceId, datasetId, { file_ids: uploads.map((item) => item.id) })
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/dataset/api/documents.ts
git commit -m "feat(dataset): extend appendDocuments API payload"
```

---

### Task 4: 前端 — `AppendChunkingStep` 组件

**Files:**
- Create: `frontend/src/features/dataset/create/AppendChunkingStep.tsx`
- Reuse CSS: `frontend/src/features/dataset/create/StepTwoChunking.css`（import 同文件）

- [ ] **Step 1: 创建组件**

参考 `DocumentSegmentConfigPanel.tsx`（只读索引/检索）与 `StepTwoChunking.tsx`（upload 预览），实现：

```tsx
/** Append flow step 1 — shared chunking config with upload preview. */
import { useQuery } from '@tanstack/react-query'
import { Form, Input, message } from 'antd'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { estimateDatasetIndexing } from '@/features/dataset/api/datasets'
import { getDataset } from '@/features/dataset/api/documents'
import { ChunkPreviewPanel, type PreviewSegment } from '@/features/dataset/create/ChunkPreviewPanel'
import { IndexingMethodPanel, type IndexingFormValues } from '@/features/dataset/create/IndexingMethodPanel'
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import { SegmentationSettingsPanel } from '@/features/dataset/create/SegmentationSettingsPanel'
import type { UploadedDatasetFile } from '@/features/dataset/create/StepTwoChunking'
import {
  ChunkingConfigPreviewLayout,
  ChunkingConfigSectionDivider,
} from '@/features/dataset/shared/ChunkingConfigPreviewLayout'
import {
  buildProcessRule,
  defaultChunkingFormValues,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'
import {
  parseRetrievalModelToForm,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'
import { getFirstFormValidationMessage } from '@/utils/formValidation'
import './StepTwoChunking.css'

export type AppendChunkingFormValues = ChunkingFormValues & IndexingFormValues & RetrievalFormValues

export type AppendChunkingStepProps = {
  datasetId: string
  uploads: UploadedDatasetFile[]
  form: FormInstance<AppendChunkingFormValues>
}

/** Chunking config for append-documents wizard (dataset-level read-only indexing/retrieval). */
export function AppendChunkingStep({ datasetId, uploads, form }: AppendChunkingStepProps) {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [previewFileId, setPreviewFileId] = useState<string | undefined>(uploads[0]?.id)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewState, setPreviewState] = useState<{
    fileId: string
    segments: PreviewSegment[]
    segmentCount: number
  } | null>(null)

  const datasetQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const embeddingOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((row) => row.enabled && row.tags.includes('EMBEDDINGS'))
        .map((row) => ({
          value: `${row.provider_name}::${row.model_name}`,
          label: `${row.provider_name} / ${row.model_name}`,
        })),
    [modelsQ.data],
  )

  const rerankOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((row) => row.enabled && row.tags.includes('RERANKING'))
        .map((row) => ({
          value: `${row.provider_name}::${row.model_name}`,
          label: `${row.provider_name} / ${row.model_name}`,
        })),
    [modelsQ.data],
  )

  const docForm = Form.useWatch('doc_form', form)
  const isHierarchical = docForm === 'hierarchical_model'

  useEffect(() => {
    const dataset = datasetQ.data
    if (!dataset) return
    const savedRule = dataset.process_rule
    const chunkingValues =
      savedRule != null ? parseProcessRuleToForm(savedRule as Record<string, unknown>) : defaultChunkingFormValues(savedRule ?? {})
    const provider = dataset.embedding_model_provider
    const model = dataset.embedding_model
    form.setFieldsValue({
      doc_form: (dataset.chunk_structure as AppendChunkingFormValues['doc_form']) ?? 'text_model',
      indexing_technique: (dataset.indexing_technique as AppendChunkingFormValues['indexing_technique']) ?? 'high_quality',
      embedding_model_key: provider && model ? `${provider}::${model}` : undefined,
      ...chunkingValues,
      ...parseRetrievalModelToForm((dataset.retrieval_model ?? {}) as Record<string, unknown>),
    })
    setPreviewFileId((current) => current ?? uploads[0]?.id)
    setPreviewState(null)
  }, [datasetQ.data, form, uploads])

  const onPreview = useCallback(async () => {
    if (!workspaceId || !previewFileId) return
    let values: AppendChunkingFormValues
    try {
      values = await form.validateFields()
    } catch (error) {
      message.error(getFirstFormValidationMessage(error) ?? t('dataset.create.validation.formIncomplete'))
      return
    }
    const defaultRule = datasetQ.data?.process_rule ?? {}
    const processRule = buildProcessRule(values, defaultRule as Record<string, unknown>)
    setPreviewLoading(true)
    try {
      const result = await estimateDatasetIndexing(workspaceId, {
        file_ids: uploads.map((item) => item.id),
        process_rule: processRule,
        indexing_technique: values.indexing_technique,
        doc_form: values.doc_form,
        preview_file_id: previewFileId,
      })
      const first = result.previews[0]
      if (first && previewFileId) {
        setPreviewState({
          fileId: previewFileId,
          segments: first.segments,
          segmentCount: first.segment_count,
        })
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('dataset.create.previewFailed'))
    } finally {
      setPreviewLoading(false)
    }
  }, [datasetQ.data?.process_rule, form, previewFileId, t, uploads, workspaceId])

  const onResetChunking = useCallback(() => {
    const savedRule = datasetQ.data?.process_rule
    if (!savedRule) return
    form.setFieldsValue(parseProcessRuleToForm(savedRule as Record<string, unknown>))
    setPreviewState(null)
  }, [datasetQ.data?.process_rule, form])

  const previewUploads = useMemo(
    () => uploads.map((item) => ({ id: item.id, name: item.name })),
    [uploads],
  )

  return (
    <ChunkingConfigPreviewLayout
      configPane={
        <Form form={form} layout="vertical">
          <Form.Item name="doc_form" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="indexing_technique" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="search_method" hidden>
            <Input />
          </Form.Item>

          <SegmentationSettingsPanel
            form={form as unknown as FormInstance<ChunkingFormValues>}
            docFormLocked
            onPreview={() => void onPreview()}
            onReset={onResetChunking}
            previewLoading={previewLoading}
          />

          <ChunkingConfigSectionDivider />

          <IndexingMethodPanel
            form={form as unknown as FormInstance<IndexingFormValues>}
            embeddingOptions={embeddingOptions}
            modelsLoading={modelsQ.isLoading}
            economyDisabled={isHierarchical}
            indexingLocked
            embeddingReadOnly
            hideEconomyDisabledHint
          />

          <ChunkingConfigSectionDivider />

          <RetrievalSettingsPanel
            form={form as unknown as FormInstance<RetrievalFormValues>}
            rerankOptions={rerankOptions}
            modelsLoading={modelsQ.isLoading}
            retrievalLocked
          />
        </Form>
      }
      previewPane={
        <ChunkPreviewPanel
          uploads={previewUploads}
          previewFileId={previewFileId}
          onPreviewFileIdChange={setPreviewFileId}
          previewState={previewState?.fileId === previewFileId ? previewState : null}
          previewLoading={previewLoading}
          onPreview={() => void onPreview()}
        />
      }
    />
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/dataset/create/AppendChunkingStep.tsx
git commit -m "feat(dataset): add AppendChunkingStep for document append wizard"
```

---

### Task 5: 前端 — `DatasetCreateWizard` 三步 append 流程

**Files:**
- Modify: `frontend/src/features/dataset/create/DatasetCreateWizard.tsx`

- [ ] **Step 1: 引入 `AppendChunkingStep` 与类型**

```typescript
import { AppendChunkingStep, type AppendChunkingFormValues } from '@/features/dataset/create/AppendChunkingStep'
```

将 append 模式表单类型改为 `Form.useForm<StepTwoFormValues | AppendChunkingFormValues>()`，或统一用 `AppendChunkingFormValues` 子集（append 不需要 `name`/`description`）。

- [ ] **Step 2: 重写 `handleAppend` — 在 Step 1 提交**

```typescript
const handleAppend = useCallback(async () => {
  if (!workspaceId || !datasetId) return
  setSubmitting(true)
  onIndexingChange?.(true)
  try {
    const values = await form.validateFields()
    setCreateSnapshot(values as StepTwoFormValues)

    const defaultRule = (await getDataset(workspaceId, datasetId)).process_rule ?? {}
    const processRule = buildProcessRule(values as StepTwoFormValues, defaultRule)

    const result = await appendDocuments(workspaceId, datasetId, {
      file_ids: uploads.map((item) => item.id),
      process_rule: processRule,
    })

    const datasetDetail = await getDataset(workspaceId, datasetId)
    setInitResult({
      datasetId,
      batch: result.batch,
      datasetName: datasetDetail.name,
      documents: result.documents.map((doc) => ({ id: doc.id, name: doc.name })),
    })
    setStep(2)
  } catch (err) {
    if (isFormValidationError(err)) {
      message.error(getFirstFormValidationMessage(err) ?? t('dataset.create.validation.formIncomplete'))
    } else {
      message.error(err instanceof Error ? err.message : t('dataset.create.initFailed'))
    }
    onIndexingChange?.(false)
  } finally {
    setSubmitting(false)
  }
}, [datasetId, form, onIndexingChange, t, uploads, workspaceId])
```

需在文件顶部增加 `import { getDataset } from '@/features/dataset/api/documents'`。

- [ ] **Step 3: 步骤条改为 append 也显示 3 步**

删除 `isAppend` 时对 Steps `items` 的两项缩短，统一：

```typescript
items={[
  { title: t('dataset.create.step1') },
  { title: t('dataset.create.step2') },
  { title: t('dataset.create.step3') },
]}
```

- [ ] **Step 4: body 区域渲染 Step 1**

```typescript
{step === 0 ? (
  <StepOneUpload ... />
) : null}
{step === 1 ? (
  isAppend ? (
    <AppendChunkingStep datasetId={datasetId!} uploads={uploads} form={form} />
  ) : (
    <StepTwoChunking workspaceId={workspaceId} uploads={uploads} form={form} />
  )
) : null}
{step === 2 && initResult ? (
  <StepThreeProcessing ... completionVariant={isAppend ? 'append' : 'create'} />
) : null}
```

调整 `minerva-dataset-create-wizard__body` 的 class：append 的 step 1 使用 split 布局（与 create step 1 相同）。

- [ ] **Step 5: footer 按钮逻辑**

```typescript
{step !== 2 ? (
  <div className="minerva-dataset-create-wizard__footer">
    <Button onClick={onCancel}>{t('common.cancel')}</Button>
    <Space>
      {step > 0 ? (
        <Button onClick={() => setStep((s) => s - 1)}>{t('dataset.create.prev')}</Button>
      ) : null}
      {step === 0 ? (
        <Button
          type="primary"
          disabled={uploads.length === 0}
          onClick={() => {
            if (isAppend) setStep(1)
            else void form.validateFields(['name']).then(() => setStep(1))
          }}
        >
          {t('dataset.create.next')}
        </Button>
      ) : null}
      {step === 1 ? (
        <Button
          type="primary"
          loading={submitting}
          onClick={() => void (isAppend ? handleAppend() : handleInit())}
        >
          {t('dataset.create.saveAndProcess')}
        </Button>
      ) : null}
    </Space>
  </div>
) : null}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/dataset/create/DatasetCreateWizard.tsx
git commit -m "feat(dataset): three-step append document wizard with chunking step"
```

---

### Task 6: 前端 — `StepThreeProcessing` 完整 append 完成页

**Files:**
- Modify: `frontend/src/features/dataset/create/StepThreeProcessing.tsx`
- Modify: `frontend/src/features/dataset/create/StepThreeProcessing.css`（若需 append 标题样式，通常可复用现有）

- [ ] **Step 1: 用 `completionVariant` 替换 `isAppend`**

```typescript
export type StepThreeProcessingProps = {
  // ...existing fields...
  completionVariant?: 'create' | 'append'
  isAppend?: boolean // 删除，改用 completionVariant
}
```

默认值 `completionVariant = 'create'`。

- [ ] **Step 2: 渲染完整布局（append 也显示摘要与侧栏）**

将 `!isAppend` 分支改为按 `completionVariant` 区分文案，结构共用：

```typescript
const isAppend = completionVariant === 'append'

// 主标题
<Typography.Title level={4} className="minerva-dataset-step-three__celebrate">
  {isAppend ? t('dataset.create.appendComplete.title') : t('dataset.create.complete.title')}
</Typography.Title>

// 副标题
<Typography.Text type="secondary" className="minerva-dataset-step-three__subtitle">
  {isAppend
    ? t('dataset.create.appendComplete.subtitle', {
        names: documents.map((d) => d.name).join('、'),
      })
    : t('dataset.create.complete.subtitle')}
</Typography.Text>

// 名称输入：仅 create 显示
{!isAppend ? ( /* Input name */ ) : null}

// 配置摘要：create 与 append 均显示（formSnapshot 存在时）
{formSnapshot ? ( /* summary rows */ ) : null}

// 操作按钮：create 与 append 均显示（append 在 allDone 前也可显示「前往文档」）
<div className="minerva-dataset-step-three__actions">
  <Button icon={<CodeOutlined />} onClick={...}>{t('dataset.create.complete.accessApi')}</Button>
  <Button type="primary" onClick={onGoToDocuments}>
    {t('dataset.create.complete.goToDocuments')}
    <ArrowRightOutlined />
  </Button>
</div>

// 侧栏：create 与 append 均显示
<aside className="minerva-dataset-step-three__aside">...</aside>
```

删除 `minerva-dataset-step-three--append` 精简样式依赖；移除 `isAppend && allDone` 才显示「完成」按钮的逻辑。

- [ ] **Step 3: 移除 `DatasetCreateWizard` 中对 `isAppend` prop 的传递，改为 `completionVariant`**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/dataset/create/StepThreeProcessing.tsx frontend/src/features/dataset/create/DatasetCreateWizard.tsx
git commit -m "feat(dataset): full completion page for append document flow"
```

---

### Task 7: i18n 文案

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 新增 append 完成页 key**

`zh-CN.json`:

```json
"dataset.create.appendComplete.title": "🎉 文档已上传",
"dataset.create.appendComplete.subtitle": "文档已上传至知识库：{{names}}，你可以在知识库的文档列表中找到它。"
```

`en.json`:

```json
"dataset.create.appendComplete.title": "🎉 Document uploaded",
"dataset.create.appendComplete.subtitle": "Uploaded to the knowledge base: {{names}}. You can find it in the document list."
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "i18n: append document completion page copy"
```

---

### Task 8: 验证

- [ ] **Step 1: 后端测试**

Run: `cd backend && pytest tests/test_document_append_chunking.py tests/test_document_segment_config.py -v`

Expected: all PASS

- [ ] **Step 2: 前端类型检查**

Run: `cd frontend && npm run build`

Expected: build succeeds

- [ ] **Step 3: 手动冒烟**

1. 打开知识库文档列表 →「添加文档」
2. 上传文件 → 按钮为「下一步」
3. 进入分段配置页：分段可编辑，索引/检索只读
4. 点击「保存并处理」→ 进入完整完成页（标题「文档已上传」、配置摘要、侧栏）
5. 嵌入完成后点击「前往文档」回到列表

---

## Spec Coverage Checklist

| Spec 需求 | Task |
|-----------|------|
| Step 0 按钮「下一步」 | Task 5 |
| Step 1 分段配置预览 | Task 4, 5 |
| 保存并处理 + process_rule | Task 2, 3, 5 |
| 每文档独立 rule 行 | Task 1, 2 |
| 完整完成页 | Task 6, 7 |
| 不传 rule 时兼容 | Task 1, 2 |
| doc_form 锁定 | Task 4 |

## 不在本计划范围

- `init_dataset` rule 共享策略变更
- 单文件进度百分比条增强
- 操作列「分段」弹窗（已完成于另一计划）
