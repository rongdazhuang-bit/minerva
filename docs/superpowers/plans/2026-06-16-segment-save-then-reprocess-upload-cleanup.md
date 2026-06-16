# 分段先保存再处理 + 知识库异步清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「保存并处理」先 commit 文档级 `process_rule` 再 reprocess；删除知识库时同步删 SQL、Celery 异步清理 upload/S3/向量，外部失败不阻断 API。

**Architecture:** `update_document` 拆两笔事务并扩展响应字段；新增 `POST .../reprocess`；`delete_dataset` 构建 cleanup manifest 后纯 SQL cascade，入队 `dataset.cleanup` 任务执行 best-effort 外部清理。

**Tech Stack:** FastAPI, SQLAlchemy async, Celery, React, Ant Design, TanStack Query, pytest

**Spec:** `docs/superpowers/specs/2026-06-16-segment-save-then-reprocess-upload-cleanup-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/app/dataset/service/document_service.py` | 两阶段 `update_document`；`reprocess_document_indexing` API 服务 |
| `backend/app/dataset/api/schemas.py` | `DatasetDocumentOut` 增加 reprocess 字段 |
| `backend/app/dataset/api/router.py` | `POST .../reprocess` |
| `backend/app/dataset/service/deletion_service.py` | `build_dataset_cleanup_manifest`；cascade 去掉同步向量删 |
| `backend/app/dataset/service/dataset_service.py` | `delete_dataset` manifest + enqueue |
| `backend/app/dataset/service/cleanup_service.py` | **新建** 异步清理业务逻辑（S3/upload/向量） |
| `backend/app/dataset/task/cleanup_task.py` | **新建** Celery 入口 |
| `backend/app/dataset/domain/constants.py` | `DATASET_CLEANUP_TASK_NAME` |
| `backend/app/celery_app.py` | import cleanup_task |
| `backend/tests/test_document_segment_save_reprocess.py` | **新建** 两阶段 + reprocess 端点 |
| `backend/tests/test_dataset_delete_cleanup.py` | **新建** manifest + cleanup 任务 |
| `frontend/src/features/dataset/api/documents.ts` | 类型 + `reprocessDocument` |
| `frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx` | 部分成功 toast |
| `frontend/src/i18n/locales/zh-CN.json` / `en.json` | `savePartialOk` 文案 |

---

## Task 1: 两阶段保存 — 失败测试

**Files:**
- Create: `backend/tests/test_document_segment_save_reprocess.py`

- [ ] **Step 1: 编写测试**

```python
"""Tests for two-phase process_rule save then reprocess."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dataset.domain.db.models import DatasetDocument, DatasetProcessRule
from app.dataset.service import document_service
from app.exceptions import AppError


def _doc_stub(*, archived: bool = False) -> DatasetDocument:
    doc = MagicMock(spec=DatasetDocument)
    doc.id = uuid.uuid4()
    doc.dataset_id = uuid.uuid4()
    doc.archived = archived
    doc.dataset_process_rule_id = uuid.uuid4()
    doc.indexing_status = "completed"
    return doc


@pytest.mark.asyncio
async def test_update_document_saves_rule_before_reprocess(monkeypatch) -> None:
    """Phase 1 commits rule; phase 2 calls reprocess and enqueue."""

    session = AsyncMock()
    commits: list = []

    async def track_commit():
        commits.append(1)

    session.commit = AsyncMock(side_effect=track_commit)
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()

    doc = _doc_stub()
    dataset = MagicMock()
    dataset.id = doc.dataset_id

    monkeypatch.setattr(
        document_service.repo,
        "get_document_for_dataset",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(document_service, "require_dataset", AsyncMock(return_value=dataset))
    reprocess = AsyncMock()
    monkeypatch.setattr(document_service, "reprocess_document", reprocess)
    enqueue = MagicMock(return_value="task-1")
    monkeypatch.setattr(document_service, "_enqueue_indexing", enqueue)

    rule_payload = {"mode": "custom", "rules": {"segmentation": {"delimiter": "\n", "max_tokens": 500}}}

    result = await document_service.update_document(
        session,
        workspace_id=uuid.uuid4(),
        dataset_id=doc.dataset_id,
        document_id=doc.id,
        user_id=uuid.uuid4(),
        patch={"process_rule": rule_payload},
    )

    assert len(commits) >= 2
    reprocess.assert_awaited_once()
    enqueue.assert_called_once()
    assert result.get("reprocess_triggered") is True
    assert result.get("reprocess_error") is None


@pytest.mark.asyncio
async def test_update_document_keeps_rule_when_reprocess_fails(monkeypatch) -> None:
    """Phase 2 failure: rule saved, reprocess_triggered false."""

    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()

    doc = _doc_stub()
    dataset = MagicMock()
    dataset.id = doc.dataset_id

    monkeypatch.setattr(
        document_service.repo,
        "get_document_for_dataset",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(document_service, "require_dataset", AsyncMock(return_value=dataset))
    monkeypatch.setattr(
        document_service,
        "reprocess_document",
        AsyncMock(side_effect=RuntimeError("vector down")),
    )
    monkeypatch.setattr(document_service, "_enqueue_indexing", MagicMock())

    with pytest.raises(AppError) as exc:
        await document_service.update_document(
            session,
            workspace_id=uuid.uuid4(),
            dataset_id=doc.dataset_id,
            document_id=doc.id,
            user_id=uuid.uuid4(),
            patch={"process_rule": {"mode": "custom", "rules": {}}},
        )

    assert exc.value.code == "dataset.reprocess_failed_after_save"
    assert session.commit.await_count >= 1
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && pytest tests/test_document_segment_save_reprocess.py -v
```

Expected: FAIL（当前单事务或未抛 `reprocess_failed_after_save`）

---

## Task 2: 实现两阶段 `update_document`

**Files:**
- Modify: `backend/app/dataset/service/document_service.py`
- Modify: `backend/app/dataset/service/document_service.py` — `_document_to_dict` 支持 reprocess 字段

- [ ] **Step 1: 抽取 `_save_document_process_rule`**

```python
async def _save_document_process_rule(
    session: AsyncSession,
    *,
    document: DatasetDocument,
    user_id: uuid.UUID,
    rule_payload: dict[str, Any],
) -> None:
    """Persist a new process_rule row and bind it to the document."""

    process_row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=document.dataset_id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=user_id,
    )
    session.add(process_row)
    await session.flush()
    document.dataset_process_rule_id = process_row.id
    document.update_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(document)
```

- [ ] **Step 2: 重写 `update_document` 中 process_rule 分支**

```python
    reprocess_triggered = None
    reprocess_error = None

    if "process_rule" in patch and patch["process_rule"] is not None:
        rule_payload = patch["process_rule"]
        await _save_document_process_rule(
            session,
            document=document,
            user_id=user_id,
            rule_payload=rule_payload,
        )
        try:
            dataset = await require_dataset(
                session, workspace_id=workspace_id, dataset_id=dataset_id
            )
            document = await repo.get_document_for_dataset(
                session,
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                document_id=document_id,
            )
            assert document is not None
            await reprocess_document(session, dataset=dataset, document=document)
            await session.commit()
            await session.refresh(document)
            _enqueue_indexing(dataset_id, [document.id])
            reprocess_triggered = True
        except Exception as exc:
            reprocess_triggered = False
            reprocess_error = "重新处理失败，配置已保存。"
            raise AppError(
                "dataset.reprocess_failed_after_save",
                reprocess_error,
                422,
            ) from exc
```

- [ ] **Step 3: `_document_to_dict` 增加可选 kwargs**

```python
def _document_to_dict(
    document: DatasetDocument,
    *,
    process_rule: dict[str, Any] | None = None,
    reprocess_triggered: bool | None = None,
    reprocess_error: str | None = None,
) -> dict[str, Any]:
    payload = { ... existing fields ... }
    if reprocess_triggered is not None:
        payload["reprocess_triggered"] = reprocess_triggered
    if reprocess_error is not None:
        payload["reprocess_error"] = reprocess_error
    return payload
```

在 `update_document` 成功返回时传入 `reprocess_triggered=True`；在 `AppError(reprocess_failed_after_save)` 前可将 document dict 附到 exception（若 router 需返回 body）— 见 Task 3。

- [ ] **Step 4: 运行 Task 1 测试**

```bash
cd backend && pytest tests/test_document_segment_save_reprocess.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataset/service/document_service.py backend/tests/test_document_segment_save_reprocess.py
git commit -m "feat(dataset): two-phase save process_rule before reprocess"
```

---

## Task 3: API schema + reprocess 端点

**Files:**
- Modify: `backend/app/dataset/api/schemas.py`
- Modify: `backend/app/dataset/api/router.py`
- Modify: `backend/app/dataset/service/document_service.py`

- [ ] **Step 1: 扩展 `DatasetDocumentOut`**

```python
class DatasetDocumentOut(BaseModel):
    # ... existing fields ...
    reprocess_triggered: bool | None = None
    reprocess_error: str | None = None
```

- [ ] **Step 2: 新增 `reprocess_document_indexing` 服务**

```python
async def reprocess_document_indexing(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """Reprocess one non-archived document and enqueue indexing."""

    document = await repo.get_document_for_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    if document is None:
        raise AppError("dataset.document_not_found", "文档不存在。", 404)
    if document.archived:
        raise AppError("dataset.document_archived", "已归档文档不可修改。", 422)
    dataset = await require_dataset(session, workspace_id=workspace_id, dataset_id=dataset_id)
    await reprocess_document(session, dataset=dataset, document=document)
    await session.commit()
    await session.refresh(document)
    _enqueue_indexing(dataset_id, [document.id])
    detail = await get_document_detail(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    detail["reprocess_triggered"] = True
    detail["reprocess_error"] = None
    return detail
```

- [ ] **Step 3: Router 注册**

```python
@router.post(
    "/{dataset_id}/documents/{document_id}/reprocess",
    response_model=DatasetDocumentOut,
)
async def reprocess_document_indexing(...):
    payload = await document_svc.reprocess_document_indexing(...)
    return DatasetDocumentOut.model_validate(payload)
```

- [ ] **Step 4: PATCH 422 时仍返回 document body（可选增强）**

若全局 exception handler 不支持，router 层 catch `AppError` code `reprocess_failed_after_save`，加载最新 document detail 填入 `reprocess_triggered=False` 后以 422 JSONResponse 返回。

- [ ] **Step 5: 测试 reprocess 端点**

在 `test_document_segment_save_reprocess.py` 增加 service 级 `test_reprocess_document_indexing_enqueues`（mock `_enqueue_indexing`）。

- [ ] **Step 6: Commit**

```bash
git add backend/app/dataset/api/schemas.py backend/app/dataset/api/router.py backend/app/dataset/service/document_service.py backend/tests/test_document_segment_save_reprocess.py
git commit -m "feat(dataset): add document reprocess endpoint and response fields"
```

---

## Task 4: 前端 — 部分成功提示

**Files:**
- Modify: `frontend/src/features/dataset/api/documents.ts`
- Modify: `frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 扩展类型与 API**

```typescript
export type DatasetDocument = {
  // ...existing...
  reprocess_triggered?: boolean | null
  reprocess_error?: string | null
}

export function reprocessDocument(
  workspaceId: string,
  datasetId: string,
  documentId: string,
) {
  return apiJson<DatasetDocument>(
    `/workspaces/${workspaceId}/datasets/${datasetId}/documents/${documentId}/reprocess`,
    { method: 'POST' },
  )
}
```

- [ ] **Step 2: `saveM.onSuccess` / `onError` 分支**

```typescript
onSuccess: (data) => {
  if (data.reprocess_triggered === false) {
    message.warning(t('dataset.documents.segmentConfig.savePartialOk'))
  } else {
    message.success(t('dataset.documents.segmentConfig.saveOk'))
  }
  setSavedSnapshot(serializeChunkingFields(form.getFieldsValue(true)))
  setPreviewState(null)
  void queryClient.invalidateQueries({ queryKey: ['dataset-document', workspaceId, datasetId, documentId] })
  void queryClient.invalidateQueries({ queryKey: ['dataset-documents', workspaceId, datasetId] })
},
onError: (err: Error & { code?: string }) => {
  if (err.code === 'dataset.reprocess_failed_after_save') {
    message.warning(t('dataset.documents.segmentConfig.savePartialOk'))
    setSavedSnapshot(serializeChunkingFields(form.getFieldsValue(true)))
    void queryClient.invalidateQueries({ queryKey: ['dataset-document', workspaceId, datasetId, documentId] })
    return
  }
  message.error(err.message)
},
```

确保 `apiJson` 将后端 `code` 挂到 Error（若尚未支持，在 client 层解析 422 body）。

- [ ] **Step 3: i18n**

```json
"dataset.documents.segmentConfig.savePartialOk": "配置已保存，重新处理失败，请稍后重试"
```

```json
"dataset.documents.segmentConfig.savePartialOk": "Settings saved, but reprocessing failed. Please retry later."
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/dataset/api/documents.ts frontend/src/features/dataset/documents/DocumentSegmentConfigPanel.tsx frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "feat(dataset): segment config partial-save UX for reprocess failures"
```

---

## Task 5: cleanup manifest — 测试

**Files:**
- Create: `backend/tests/test_dataset_delete_cleanup.py`

- [ ] **Step 1: 编写 manifest 测试**

```python
"""Tests for dataset delete cleanup manifest and async task."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.domain.db.models import DatasetDocument, DatasetUploadFile
from app.dataset.service.deletion_service import build_dataset_cleanup_manifest


def _doc(file_id: uuid.UUID, dataset_id: uuid.UUID, workspace_id: uuid.UUID) -> DatasetDocument:
    d = MagicMock(spec=DatasetDocument)
    d.file_id = str(file_id)
    d.dataset_id = dataset_id
    d.workspace_id = workspace_id
    d.data_source_info = json.dumps({"upload_file_id": str(file_id)})
    return d


@pytest.mark.asyncio
async def test_manifest_excludes_cross_dataset_shared_upload() -> None:
    session = AsyncMock()
    workspace_id = uuid.uuid4()
    dataset_a = uuid.uuid4()
    upload_id = uuid.uuid4()
    docs = [_doc(upload_id, dataset_a, workspace_id)]

    upload_row = DatasetUploadFile(
        id=upload_id,
        workspace_id=workspace_id,
        storage_key="dataset/uploads/x.txt",
        name="x.txt",
        size=1,
        extension="txt",
        created_by=uuid.uuid4(),
    )
    session.get = AsyncMock(return_value=upload_row)
    session.scalar = AsyncMock(return_value=1)  # other dataset still references

    manifest = await build_dataset_cleanup_manifest(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_a,
        documents=docs,
        indexing_technique="economy",
    )

    assert manifest["uploads"] == []
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && pytest tests/test_dataset_delete_cleanup.py -v
```

Expected: FAIL（`build_dataset_cleanup_manifest` 不存在）

---

## Task 6: 实现 manifest + 调整 cascade

**Files:**
- Modify: `backend/app/dataset/service/deletion_service.py`
- Modify: `backend/app/dataset/service/dataset_service.py`

- [ ] **Step 1: 新增 manifest 类型与 builder**

```python
from typing import TypedDict

class DatasetCleanupUpload(TypedDict):
    id: str
    storage_key: str

class DatasetCleanupManifest(TypedDict):
    workspace_id: str
    dataset_id: str
    indexing_technique: str | None
    uploads: list[DatasetCleanupUpload]


async def _collect_upload_id(document: DatasetDocument) -> uuid.UUID | None:
    if document.file_id:
        try:
            return uuid.UUID(str(document.file_id))
        except ValueError:
            pass
    raw = document.data_source_info
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return None
    uid = info.get("upload_file_id")
    if not uid:
        return None
    try:
        return uuid.UUID(str(uid))
    except ValueError:
        return None


async def _upload_referenced_elsewhere(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    upload_id: uuid.UUID,
    exclude_dataset_id: uuid.UUID,
) -> bool:
    from sqlalchemy import func, select
    from app.dataset.domain.db.models import DatasetDocument

    count = await session.scalar(
        select(func.count())
        .select_from(DatasetDocument)
        .where(
            DatasetDocument.workspace_id == workspace_id,
            DatasetDocument.dataset_id != exclude_dataset_id,
            DatasetDocument.file_id == str(upload_id),
        )
    )
    return int(count or 0) > 0


async def build_dataset_cleanup_manifest(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    documents: list[DatasetDocument],
    indexing_technique: str | None,
) -> DatasetCleanupManifest:
    uploads: list[DatasetCleanupUpload] = []
    seen: set[uuid.UUID] = set()
    for doc in documents:
        upload_id = await _collect_upload_id(doc)
        if upload_id is None or upload_id in seen:
            continue
        seen.add(upload_id)
        if await _upload_referenced_elsewhere(
            session,
            workspace_id=workspace_id,
            upload_id=upload_id,
            exclude_dataset_id=dataset_id,
        ):
            continue
        row = await session.get(DatasetUploadFile, upload_id)
        if row is None:
            continue
        uploads.append({"id": str(row.id), "storage_key": row.storage_key})
    return {
        "workspace_id": str(workspace_id),
        "dataset_id": str(dataset_id),
        "indexing_technique": indexing_technique,
        "uploads": uploads,
    }
```

- [ ] **Step 2: `delete_dataset_cascade` 移除 `delete_vector_collection`**

```python
async def delete_dataset_cascade(
    session: AsyncSession,
    *,
    dataset: Dataset,
) -> None:
    # ... existing SQL deletes ...
    # 删除末尾的 await delete_vector_collection(dataset)
    await session.delete(dataset)
```

- [ ] **Step 3: `delete_dataset` 集成**

```python
async def delete_dataset(...) -> None:
    row = await require_dataset(...)
    docs = list(
        (
            await session.scalars(
                select(DatasetDocument).where(DatasetDocument.dataset_id == dataset_id)
            )
        ).all()
    )
    manifest = await build_dataset_cleanup_manifest(
        session,
        workspace_id=row.workspace_id,
        dataset_id=row.id,
        documents=docs,
        indexing_technique=row.indexing_technique,
    )
    await delete_dataset_cascade(session, dataset=row)
    await session.commit()
    _enqueue_dataset_cleanup(manifest)
```

- [ ] **Step 4: 运行 Task 5 测试 PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/dataset/service/deletion_service.py backend/app/dataset/service/dataset_service.py backend/tests/test_dataset_delete_cleanup.py
git commit -m "feat(dataset): build cleanup manifest on dataset delete"
```

---

## Task 7: Celery cleanup 任务

**Files:**
- Create: `backend/app/dataset/service/cleanup_service.py`
- Create: `backend/app/dataset/task/cleanup_task.py`
- Modify: `backend/app/dataset/domain/constants.py`
- Modify: `backend/app/celery_app.py`
- Modify: `backend/tests/test_dataset_delete_cleanup.py`

- [ ] **Step 1: 常量**

```python
DATASET_CLEANUP_TASK_NAME = "dataset.cleanup"
```

- [ ] **Step 2: `run_dataset_cleanup` 服务**

```python
async def run_dataset_cleanup(session: AsyncSession, manifest: dict[str, Any]) -> dict[str, int]:
    workspace_id = uuid.UUID(manifest["workspace_id"])
    dataset_id = uuid.UUID(manifest["dataset_id"])
    indexing_technique = manifest.get("indexing_technique")
    summary = {"s3_deleted": 0, "s3_failed": 0, "upload_rows_deleted": 0, "vector_dropped": 0}

    s3 = S3FileService(session=session)
    for item in manifest.get("uploads") or []:
        upload_id = uuid.UUID(item["id"])
        storage_key = item["storage_key"]
        if await _upload_referenced_elsewhere(
            session,
            workspace_id=workspace_id,
            upload_id=upload_id,
            exclude_dataset_id=dataset_id,
        ):
            continue
        try:
            await s3.delete_file(workspace_id=workspace_id, object_key=storage_key)
            summary["s3_deleted"] += 1
        except Exception:
            log.exception("dataset.cleanup s3_failed dataset_id={} upload_id={}", dataset_id, upload_id)
            summary["s3_failed"] += 1
        try:
            row = await session.get(DatasetUploadFile, upload_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
                summary["upload_rows_deleted"] += 1
        except Exception:
            log.exception("dataset.cleanup upload_row_failed upload_id={}", upload_id)
            await session.rollback()

    if indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:
        try:
            stub = type("DatasetStub", (), {"id": dataset_id, "indexing_technique": indexing_technique})()
            await delete_vector_collection(stub)  # type: ignore[arg-type]
            summary["vector_dropped"] = 1
        except Exception:
            log.exception("dataset.cleanup vector_failed dataset_id={}", dataset_id)

    return summary
```

`delete_vector_collection` 需 `Dataset` 实例 — 实现时用轻量 stub 或抽取 `delete_vector_collection_by_id(dataset_id, indexing_technique)`。

- [ ] **Step 3: Celery task（仿 `indexing_task.py`）**

```python
@shared_task(bind=True, name=DATASET_CLEANUP_TASK_NAME)
def dataset_cleanup_task(self: Task, manifest: dict[str, Any]) -> dict[str, Any]:
    log.info("dataset.cleanup start dataset_id={}", manifest.get("dataset_id"))
    return _run_async(manifest)


def _run_async(manifest: dict[str, Any]) -> dict[str, Any]:
    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_dataset_cleanup(session, manifest)
        finally:
            await engine.dispose(close=True)
    return asyncio.run(_runner())
```

- [ ] **Step 4: `_enqueue_dataset_cleanup` in `dataset_service.py`**

```python
def _enqueue_dataset_cleanup(manifest: dict[str, Any]) -> str | None:
    if celery_app is None:
        log.warning("dataset.cleanup skipped: celery unavailable dataset_id={}", manifest.get("dataset_id"))
        return None
    try:
        result = celery_app.send_task(
            DATASET_CLEANUP_TASK_NAME,
            args=[manifest],
            queue="dataset",
        )
        return str(result.id)
    except Exception:
        log.exception("dataset.cleanup enqueue_failed dataset_id={}", manifest.get("dataset_id"))
        return None
```

- [ ] **Step 5: `celery_app.py` 增加 import**

```python
import app.dataset.task.cleanup_task  # noqa: F401
```

- [ ] **Step 6: 任务单测 — S3 失败仍删 upload 行**

```python
@pytest.mark.asyncio
async def test_cleanup_continues_when_s3_fails(monkeypatch) -> None:
    # mock s3.delete_file raise; assert upload row delete attempted; no exception
```

- [ ] **Step 7: 全量测试**

```bash
cd backend && pytest tests/test_dataset_delete_cleanup.py tests/test_document_segment_save_reprocess.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/dataset/service/cleanup_service.py backend/app/dataset/task/cleanup_task.py backend/app/dataset/domain/constants.py backend/app/celery_app.py backend/tests/test_dataset_delete_cleanup.py
git commit -m "feat(dataset): async Celery cleanup for uploads S3 and vectors on delete"
```

---

## Task 8: Spec 状态回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-16-segment-save-then-reprocess-upload-cleanup-design.md`

- [ ] **Step 1: 将状态改为「已实现」并勾选验收标准（实现完成后）**

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-06-16-segment-save-then-reprocess-upload-cleanup-design.md
git commit -m "docs: mark segment save-reprocess and dataset cleanup spec implemented"
```

---

## Spec Coverage Self-Review

| Spec 要求 | Task |
|-----------|------|
| 两阶段 save + reprocess | Task 1–2 |
| 阶段 2 失败策略 A + 422 | Task 2–3 |
| POST reprocess | Task 3 |
| 前端部分成功 toast | Task 4 |
| 同步 SQL cascade | Task 6 |
| async upload/S3/vector | Task 7 |
| 跨库 upload 跳过 | Task 5–6 |
| Celery 不可用降级 | Task 7 Step 4 |
| 日志 best-effort | Task 7 Step 2 |

---

## Verification

```bash
cd backend && pytest tests/test_document_segment_save_reprocess.py tests/test_dataset_delete_cleanup.py -v
```

Manual: 分段弹窗保存并处理 → 列表 indexing 轮询；删除知识库 → 204 立即消失 → worker 日志出现 `dataset.cleanup`。
