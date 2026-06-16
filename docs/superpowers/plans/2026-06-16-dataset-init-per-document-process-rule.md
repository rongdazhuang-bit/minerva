# 创建知识库 — 每文档独立 process_rule 行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建知识库时，N 个文件创建 N 条 `dataset_process_rule` 记录（配置内容相同、id 不同），与 `append_documents` 行为对齐。

**Architecture:** 在 `init_dataset_with_documents` 的文件循环内为每个文档插入独立 `DatasetProcessRule`；抽取与 `append_documents` 共用的创建 helper 避免重复；仅改后端 init 路径，无 schema / 前端 / 历史数据迁移。

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-06-16-dataset-init-per-document-process-rule-design.md`

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/tests/test_dataset_init_process_rule.py` | init 多文件 → 多 rule 行单元测试 |
| `backend/app/dataset/service/process_rule_service.py` | 新建：共用 `create_process_rule_row` |
| `backend/app/dataset/service/init_service.py` | 循环内按文档创建 rule 并绑定 |
| `backend/app/dataset/service/document_service.py` | `append_documents` 改用共用 helper |

---

### Task 1: 后端 — init 每文档 rule 行测试

**Files:**
- Create: `backend/tests/test_dataset_init_process_rule.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for init_dataset_with_documents per-document process_rule rows."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.domain.constants import INDEXING_TECHNIQUE_ECONOMY
from app.dataset.domain.db.models import DatasetDocument, DatasetProcessRule
from app.dataset.service import init_service


def _upload_stub(upload_id: uuid.UUID, workspace_id: uuid.UUID, name: str = "demo.txt"):
    return type(
        "UploadStub",
        (),
        {"id": upload_id, "workspace_id": workspace_id, "name": name},
    )()


@pytest.mark.asyncio
async def test_init_creates_process_rule_per_document(monkeypatch) -> None:
    """Each document in init gets its own DatasetProcessRule row with identical rules."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    file_id_a = uuid.uuid4()
    file_id_b = uuid.uuid4()
    added: list = []

    session.add = MagicMock(side_effect=lambda row: added.append(row))
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    uploads = {
        file_id_a: _upload_stub(file_id_a, workspace_id, "a.txt"),
        file_id_b: _upload_stub(file_id_b, workspace_id, "b.txt"),
    }

    async def fake_get(session_obj, model, upload_id):
        _ = session_obj, model
        return uploads.get(upload_id)

    session.get = AsyncMock(side_effect=fake_get)

    enqueue_ids: list[uuid.UUID] = []

    def fake_enqueue(ds_id, doc_ids):
        _ = ds_id
        enqueue_ids.extend(doc_ids)
        return "task-1"

    monkeypatch.setattr(init_service, "_enqueue_indexing", fake_enqueue)

    process_rule = {
        "mode": "custom",
        "rules": {
            "pre_processing_rules": [],
            "segmentation": {"delimiter": "\n", "max_tokens": 500, "chunk_overlap": 50},
        },
    }

    result = await init_service.init_dataset_with_documents(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        name="Test KB",
        description=None,
        indexing_technique=INDEXING_TECHNIQUE_ECONOMY,
        doc_form="text_model",
        file_ids=[file_id_a, file_id_b],
        process_rule=process_rule,
        retrieval_model=None,
        embedding_model=None,
        embedding_model_provider=None,
    )

    rule_rows = [r for r in added if isinstance(r, DatasetProcessRule)]
    doc_rows = [r for r in added if isinstance(r, DatasetDocument)]

    assert len(rule_rows) == 2
    assert len(doc_rows) == 2
    assert len(result["documents"]) == 2

    rules_payloads = [json.loads(r.rules) for r in rule_rows]
    assert rules_payloads[0] == rules_payloads[1] == process_rule

    rule_ids = {r.id for r in rule_rows}
    assert len(rule_ids) == 2

    doc_rule_ids = {d.dataset_process_rule_id for d in doc_rows}
    assert doc_rule_ids == rule_ids
    assert doc_rows[0].dataset_process_rule_id != doc_rows[1].dataset_process_rule_id

    assert len(enqueue_ids) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run（在 `backend/` 目录）:

```bash
pytest tests/test_dataset_init_process_rule.py::test_init_creates_process_rule_per_document -v
```

Expected: FAIL — `len(rule_rows) == 1`（当前仅创建一条共享 rule）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_dataset_init_process_rule.py
git commit -m "test(dataset): expect per-document process_rule on init"
```

---

### Task 2: 后端 — 共用 process_rule 创建 helper

**Files:**
- Create: `backend/app/dataset/service/process_rule_service.py`
- Modify: `backend/app/dataset/service/document_service.py`（`append_documents` 内联创建改为调用 helper）

- [ ] **Step 1: 新建 helper 模块**

```python
"""Shared helpers for dataset_process_rule persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import DatasetProcessRule
from app.dataset.service.chunk_service import serialize_process_rule


async def create_process_rule_row(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    rule_payload: dict[str, Any],
) -> uuid.UUID:
    """Insert one DatasetProcessRule row and return its id."""

    row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    return row.id
```

- [ ] **Step 2: `append_documents` 改用 helper**

在 `backend/app/dataset/service/document_service.py` 顶部增加：

```python
from app.dataset.service.process_rule_service import create_process_rule_row
```

将 `append_documents` 循环内：

```python
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
```

替换为：

```python
        if process_rule is not None:
            rule_id = await create_process_rule_row(
                session,
                dataset_id=dataset.id,
                user_id=user_id,
                rule_payload=process_rule,
            )
```

若 `serialize_process_rule` 在 `document_service` 中仅被此处使用，可移除对应 import（保留 PATCH 等其它引用处仍需要的 import）。

- [ ] **Step 3: 运行已有 dataset 相关测试（若有 append 测试则一并跑）**

```bash
pytest tests/test_dataset_init_process_rule.py tests/test_document_append_chunking.py -v
```

Expected: init 测试仍 FAIL；append 行为不变 PASS（若无 append 测试文件则仅跑 init）

- [ ] **Step 4: Commit**

```bash
git add backend/app/dataset/service/process_rule_service.py backend/app/dataset/service/document_service.py
git commit -m "refactor(dataset): extract create_process_rule_row helper"
```

---

### Task 3: 后端 — `init_dataset_with_documents` 每文档 rule

**Files:**
- Modify: `backend/app/dataset/service/init_service.py`

- [ ] **Step 1: 修改 init 循环逻辑**

顶部增加 import：

```python
from app.dataset.service.process_rule_service import create_process_rule_row
```

删除循环外的单次创建（约 L115–122）：

```python
    process_row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=user_id,
    )
    session.add(process_row)
```

在 `for position, upload_id in enumerate(file_ids, start=1):` 内、`upload` 校验通过后、创建 `DatasetDocument` 之前插入：

```python
        rule_id = await create_process_rule_row(
            session,
            dataset_id=dataset.id,
            user_id=user_id,
            rule_payload=rule_payload,
        )
```

将 `DatasetDocument` 的 `dataset_process_rule_id=process_row.id` 改为 `dataset_process_rule_id=rule_id`。

移除不再使用的 import：`DatasetProcessRule`、`serialize_process_rule`（若 init_service 内无其它引用）。

- [ ] **Step 2: 运行测试确认通过**

```bash
pytest tests/test_dataset_init_process_rule.py::test_init_creates_process_rule_per_document -v
```

Expected: PASS

- [ ] **Step 3: 运行相关回归**

```bash
pytest tests/test_dataset_init_process_rule.py tests/test_dataset_api.py tests/test_dataset_integration.py -v
```

（若部分文件不存在则跳过；至少 init 测试必须通过）

- [ ] **Step 4: Commit**

```bash
git add backend/app/dataset/service/init_service.py
git commit -m "feat(dataset): create per-document process_rule on knowledge base init"
```

---

## 验收对照（Spec §验收标准）

| 验收项 | 对应 Task |
|--------|-----------|
| 2+ 文件 → rule 行数 = 文件数 | Task 1 + Task 3 |
| 各 rule `mode`/`rules` 相同 | Task 1 断言 |
| 各文档 `dataset_process_rule_id` 不同 | Task 1 断言 |
| 历史数据不变 | 无迁移任务 |
| API/前端不变 | 无改动 |

---

## 手动冒烟（可选）

1. 创建知识库向导上传 2 个文件，完成索引  
2. 在 DB 查询：`SELECT COUNT(*) FROM dataset_process_rule WHERE dataset_id = ?` 应为 2  
3. 分别打开两个文档的分段配置弹窗，确认可独立加载（rule id 不同）
