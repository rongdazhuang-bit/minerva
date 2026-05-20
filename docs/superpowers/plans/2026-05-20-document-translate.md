# 多格式文档翻译 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付工作区「文档翻译 → 翻译」全链路：六种格式上传、源/目标语言 + `translate` 模型选择、Celery 单任务流水线（含扫描 PDF 自动 OCR）、左右段落对照与译文下载。

**Architecture:** 后端 `app/translate` 以统一段落中间模型驱动：后缀策略 `extract → translate_llm（逐段）→ assemble`；`doc_translate_job` / `doc_translate_segment` 持久化；扫描 PDF 经 `ocr_bridge` 创建 `ocr_file` 并轮询 SUCCESS 后再映射段落。前端 `features/translate` 复用 `AgentsPage` 双栏布局，首期 3s HTTP 轮询进度。

**Tech Stack:** FastAPI, SQLAlchemy async, Celery, Pydantic v2, python-docx, openpyxl, pymupdf, React 18, Ant Design, TanStack Query, i18next.

**设计依据:** `docs/superpowers/specs/2026-05-20-document-translate-design.md`

---

## 文件结构（将创建 / 将修改）

### 后端（新建）

- `backend/app/translate/__init__.py`
- `backend/app/translate/domain/constants.py` — 状态、后缀白名单、Celery 名、大小上限
- `backend/app/translate/domain/db/models.py` — `DocTranslateJob`, `DocTranslateSegment`
- `backend/app/translate/domain/dto.py` — `SegmentDraft`, `SegmentRecord`
- `backend/app/translate/infrastructure/repository.py` — CRUD、keyset 列表、批量 segment
- `backend/app/translate/service/strategies/base.py`
- `backend/app/translate/service/strategies/registry.py`
- `backend/app/translate/service/strategies/txt.py`, `md.py`, `csv.py`, `xlsx.py`, `docx.py`, `pdf.py`
- `backend/app/translate/service/translate_llm.py`
- `backend/app/translate/service/ocr_bridge.py`
- `backend/app/translate/service/run_pipeline.py`
- `backend/app/translate/service/job_service.py`
- `backend/app/translate/service/job_delete.py`
- `backend/app/translate/task/run_job.py`
- `backend/app/translate/api/schemas.py`
- `backend/app/translate/api/router.py`
- `backend/tests/test_doc_translate_strategies_txt_md_csv.py`
- `backend/tests/test_doc_translate_api.py`

### 后端（修改）

- `backend/sql/schema_postgresql.sql` — `doc_translate_job` / `doc_translate_segment` 建表（无 FK）
- `backend/app/core/infrastructure/db/bootstrap.py` — `_import_models` 增加 translate models
- `backend/app/core/api/router.py` — 注册 translate router
- `backend/app/celery_app.py` — `import app.translate.task.run_job`
- `backend/app/config.py` — `doc_translate_max_file_bytes`, `doc_translate_segment_concurrency`, `doc_translate_ocr_poll_*`
- `backend/.env.example`, `backend/.env.dev` — 同步新环境变量
- `backend/pyproject.toml` — `python-docx`, `openpyxl`, `pymupdf`

### 前端（新建）

- `minerva-ui/src/api/translate.ts`
- `minerva-ui/src/features/translate/TranslatePage.tsx`
- `minerva-ui/src/features/translate/TranslatePage.css`
- `minerva-ui/src/features/translate/translateJobUi.ts`
- `minerva-ui/src/features/translate/index.ts`

### 前端（修改 / 删除）

- `minerva-ui/src/app/router.tsx` — `/app/translate`，移除 `doc-translate`
- `minerva-ui/src/app/layout/AppLayout.tsx` — 菜单路径、`menuKeyForPath`、`contentScrollStyleForPath`
- `minerva-ui/src/app/layout/AppBreadcrumb.tsx`
- `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`
- 删除 `minerva-ui/src/features/doc-translate/`（两处文件）

---

## Task 1: 数据库表与 ORM

**Files:**
- Modify: `backend/sql/schema_postgresql.sql`
- Create: `backend/app/translate/domain/db/models.py`
- Create: `backend/app/translate/domain/constants.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Create: `backend/tests/test_doc_translate_models.py`

- [ ] **Step 1: 写失败测试（表名与关键列存在）**

```python
# backend/tests/test_doc_translate_models.py
from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment


def test_doc_translate_job_tablename() -> None:
    assert DocTranslateJob.__tablename__ == "doc_translate_job"


def test_doc_translate_segment_tablename() -> None:
    assert DocTranslateSegment.__tablename__ == "doc_translate_segment"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_doc_translate_models.py -v
```

Expected: `ModuleNotFoundError` 或 import 失败。

- [ ] **Step 3: 实现 ORM + SQL + bootstrap**

`DocTranslateJob` / `DocTranslateSegment` 字段按 spec §3；`UUID` 列无 `ForeignKey`；`DocTranslateJob` 加 `Index("ix_doc_translate_job_workspace_updated", "workspace_id", "updated_at")`。

`constants.py` 至少：

```python
DOC_TRANSLATE_RUN_TASK_NAME = "translate.run_job"
DOC_TRANSLATE_ALLOWED_EXTS = frozenset({"docx", "pdf", "txt", "md", "csv", "xlsx"})
DOC_TRANSLATE_STATUS_PENDING = "PENDING"
# ... OCR_RUNNING, EXTRACTING, TRANSLATING, ASSEMBLING, SUCCESS, FAILED
DOC_TRANSLATE_SEGMENT_PENDING = "PENDING"
DOC_TRANSLATE_SEGMENT_DONE = "DONE"
DOC_TRANSLATE_SEGMENT_FAILED = "FAILED"
DOC_TRANSLATE_MAX_FILE_BYTES = 20 * 1024 * 1024
DOC_TRANSLATE_LIST_DEFAULT_LIMIT = 20
```

`bootstrap._import_models` 追加：

```python
import app.translate.domain.db.models  # noqa: F401
```

`schema_postgresql.sql` 追加两段 `CREATE TABLE`（与 ORM 一致，文件头约定：禁止 FK）。

- [ ] **Step 4: 重跑测试**

```bash
cd backend && pytest tests/test_doc_translate_models.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/sql/schema_postgresql.sql backend/app/translate backend/app/core/infrastructure/db/bootstrap.py backend/tests/test_doc_translate_models.py
git commit -m "feat(translate): add doc_translate_job and doc_translate_segment schema"
```

---

## Task 2: Repository 与 keyset 游标

**Files:**
- Create: `backend/app/translate/infrastructure/repository.py`
- Create: `backend/tests/test_doc_translate_repository_cursor.py`

- [ ] **Step 1: 写游标编解码单测**

```python
from datetime import UTC, datetime
import uuid
from app.translate.infrastructure.repository import (
    decode_doc_translate_job_cursor,
    encode_doc_translate_job_cursor,
)

def test_job_cursor_roundtrip() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    jid = uuid.uuid4()
    raw = encode_doc_translate_job_cursor(ts, jid)
    got_ts, got_id = decode_doc_translate_job_cursor(raw)
    assert got_id == jid
    assert got_ts == ts
```

- [ ] **Step 2: 运行确认 FAIL**

```bash
cd backend && pytest tests/test_doc_translate_repository_cursor.py -v
```

- [ ] **Step 3: 实现 repository**

函数清单（复制 `agent_session` 模式）：

- `encode_doc_translate_job_cursor` / `decode_doc_translate_job_cursor`
- `create_doc_translate_job`
- `get_doc_translate_job`
- `list_doc_translate_jobs_recent` → `(rows, has_more)`
- `update_job_status(...)` — status, progress, segment_total/done, error_*, ocr_file_id, result_object_key
- `bulk_insert_segments`
- `list_segments_by_job` — 按 `seq` 升序
- `delete_doc_translate_job_dependents` — 先 segment 后 job

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(translate): add repository and job list cursor helpers"
```

---

## Task 3: 策略基类 + 注册表 + txt/md/csv

**Files:**
- Create: `backend/app/translate/domain/dto.py`
- Create: `backend/app/translate/service/strategies/base.py`
- Create: `backend/app/translate/service/strategies/registry.py`
- Create: `backend/app/translate/service/strategies/txt.py`, `md.py`, `csv.py`
- Create: `backend/tests/test_doc_translate_strategies_txt_md_csv.py`

- [ ] **Step 1: 写 roundtrip 失败测试**

对临时文件：

- `hello\n\nworld` txt → 2 段 → assemble → 文件内容仍含两段
- md  fenced code 块保持单段
- csv 两行 → 2 段

- [ ] **Step 2: FAIL 后实现**

`SegmentDraft`: `seq: int`, `source_text: str`, `anchor_json: dict | None`。

`registry.get_doc_translate_strategy(ext)` 小写后缀；未知抛 `KeyError`。

`md.py`：按空行分段；`` ``` `` 块整体为一段（正则或状态机，与 spec 一致）。

`csv.py`：一行一段，`anchor_json={"row": n}`。

- [ ] **Step 3: pytest PASS**

```bash
cd backend && pytest tests/test_doc_translate_strategies_txt_md_csv.py -v
```

- [ ] **Step 4: Commit**

---

## Task 4: xlsx 与 docx 策略

**Files:**
- Create: `backend/app/translate/service/strategies/xlsx.py`, `docx.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/test_doc_translate_strategies_office.py`

- [ ] **Step 1: 添加依赖**

`pyproject.toml`:

```toml
"python-docx>=1.1",
"openpyxl>=3.1",
```

安装：`cd backend && pip install -e ".[dev]"`（或项目惯用命令）。

- [ ] **Step 2: 写最小样例测试**

- xlsx：2 行 2 列写入测试文件，extract 段数 ≥ 2，assemble 后 B2 译文替换
- docx：两段段落 + 简单 bold run，assemble 后段落数不变

- [ ] **Step 3: 实现策略并 PASS**

`xlsx`：`anchor_json={"sheet": name, "row": r, "cells": [col,...]}`。  
`docx`：`anchor_json={"kind": "paragraph", "index": i}` 或 table 坐标。

- [ ] **Step 4: Commit**

---

## Task 5: pdf 策略 + OCR 检测

**Files:**
- Modify: `backend/pyproject.toml` — `pymupdf>=1.24`
- Create: `backend/app/translate/service/strategies/pdf.py`
- Create: `backend/tests/test_doc_translate_pdf_needs_ocr.py`

- [ ] **Step 1: `needs_ocr` 单测**

- 纯图片 PDF 样例（或 mock fitz）→ `True`
- 含可复制文本 PDF → `False`

- [ ] **Step 2: 实现 pdf 策略**

- 文本层：`extract` 按 block/line 合并为段，`anchor_json` 含 `page`, `bbox`
- `assemble`：PyMuPDF `add_redact_annot` + `apply_redactions` + `insert_text`（或项目选定 API）写回
- `needs_ocr`：总字符数 &lt; 阈值（如 32）视为扫描件

扫描件 `extract(..., ocr_file_id=...)`：调用 `get_ocr_file_markdown_pages` 逻辑（见 Task 6）将每页/块转为 `SegmentDraft`。

- [ ] **Step 3: pytest PASS**

- [ ] **Step 4: Commit**

---

## Task 6: OCR 桥接

**Files:**
- Create: `backend/app/translate/service/ocr_bridge.py`
- Create: `backend/tests/test_doc_translate_ocr_bridge.py`（mock DB / httpx）

- [ ] **Step 1: 实现 `ensure_ocr_for_pdf`**

流程：

1. 用 `file_ocr` 相同字段创建 `OcrFile`（`status=INIT`，`ocr_type` 取工作区默认：查询 `TOOL_OCR` 字典首项或配置 `DOC_TRANSLATE_DEFAULT_OCR_TYPE`）
2. `object_key` 复用 translate 源 PDF 的 key（或复制到 `ocr_file/` 前缀 — 与产品一致即可，spec 允许复用源 key）
3. 轮询 `OcrFile.status` 每 2s，直至 `SUCCESS`/`FAILED` 或超时（`settings.doc_translate_ocr_timeout_seconds`，默认 1800）
4. 返回 `ocr_file_id`；失败抛 `AppError("translate.ocr_failed", ...)`

**不删除** OCR 行；仅写 `doc_translate_job.ocr_file_id`。

- [ ] **Step 2: 单测 mock 状态流转**

- [ ] **Step 3: Commit**

---

## Task 7: translate_llm + run_pipeline

**Files:**
- Create: `backend/app/translate/service/translate_llm.py`
- Create: `backend/app/translate/service/run_pipeline.py`
- Create: `backend/tests/test_doc_translate_translate_llm.py`（mock `chat_service.complete`）

- [ ] **Step 1: `translate_llm.translate_segment`**

- `model_repo.get_for_workspace` 校验 `model_type` 在 `MODEL_TYPE` 字典且 code 为 `translate`（与 `model_provider_service._validate_model_fields` 一致）
- `chat_service.complete(..., temperature=0.2)`；system prompt 含源/目标语言；user 仅段落文本
- 返回 stripped 译文

- [ ] **Step 2: `run_pipeline.run_job_once(session, job_id)`**

顺序（更新 status）：

1. `PENDING` → 下载 S3 源到 `tempfile.TemporaryDirectory`
2. 若 pdf 且 `needs_ocr` → `OCR_RUNNING` + `ocr_bridge`
3. `EXTRACTING` → `strategy.extract` → `bulk_insert_segments` + `segment_total`
4. `TRANSLATING` → `asyncio.Semaphore(settings.doc_translate_segment_concurrency)` 逐段翻译；更新 `segment_done`/`progress`；任一段失败 → `FAILED` 并 return
5. `ASSEMBLING` → `assemble` → S3 upload `translate/result/{workspace_id}/{job_id}.{ext}`
6. `SUCCESS`

异常统一写 `error_code`/`error_message`。

- [ ] **Step 3: mock LLM 单测 pipeline 对 txt 样例 SUCCESS**

- [ ] **Step 4: Commit**

---

## Task 8: Celery 任务与配置

**Files:**
- Create: `backend/app/translate/task/run_job.py`
- Modify: `backend/app/celery_app.py`
- Modify: `backend/app/config.py`, `backend/.env.example`, `backend/.env.dev`

- [ ] **Step 1: Celery task（复制 `scan_init_job` 模式）**

```python
@shared_task(bind=True, name=DOC_TRANSLATE_RUN_TASK_NAME)
def run_doc_translate_job(self: Task, job_id: str) -> dict[str, Any]:
    async def _runner() -> dict[str, Any]:
        await engine.dispose(close=True)
        try:
            async with async_session_factory() as session:
                return await run_pipeline.run_job_once(session, uuid.UUID(job_id))
        finally:
            await engine.dispose(close=True)
    ...
```

- [ ] **Step 2: `celery_app.py` 注册 import**

```python
import app.translate.task.run_job  # noqa: F401
```

- [ ] **Step 3: Settings**

```python
doc_translate_max_file_bytes: int = 20 * 1024 * 1024
doc_translate_segment_concurrency: int = 5
doc_translate_ocr_poll_interval_seconds: float = 2.0
doc_translate_ocr_timeout_seconds: int = 1800
doc_translate_default_ocr_type: str = "PADDLE_OCR"  # 与 file_ocr 常量对齐
```

同步 `.env.example` / `.env.dev`。

- [ ] **Step 4: 本地手动验证（可选）**

启动 worker 后 `enqueue_task(DOC_TRANSLATE_RUN_TASK_NAME, args=[str(job_id)])`。

- [ ] **Step 5: Commit**

---

## Task 9: HTTP API

**Files:**
- Create: `backend/app/translate/api/schemas.py`
- Create: `backend/app/translate/api/router.py`
- Create: `backend/app/translate/service/job_service.py`
- Create: `backend/app/translate/service/job_delete.py`
- Modify: `backend/app/core/api/router.py`
- Create: `backend/tests/test_doc_translate_api.py`

- [ ] **Step 1: 写 API 集成测试骨架**

Fixtures：登录、workspace、`MODEL_TYPE` 字典含 `translate` 项、创建 translate 模型、上传小 txt。

断言：

- `POST /translate/jobs` → 201 + `id`
- `GET /translate/jobs` 含该项
- mock Celery enqueue（monkeypatch `enqueue_task`）避免真 worker

- [ ] **Step 2: 实现 `job_service.create_job`**

- S3 `module_prefix="translate/source"`
- 校验后缀、大小、`model_id`
- 插入 `doc_translate_job` `PENDING`
- `enqueue_task(DOC_TRANSLATE_RUN_TASK_NAME, args=[str(job.id)])`

- [ ] **Step 3: 实现其余路由**

| 路由 | 要点 |
|------|------|
| `GET /jobs` | cursor + limit |
| `GET /jobs/{id}` | 详情 |
| `GET /jobs/{id}/segments` | limit 5000 |
| `GET /jobs/{id}/download` | `S3FileService` 重定向或流 |
| `DELETE /jobs/{id}` | `job_delete` 清 segment + S3 + job |

`router` prefix: `/workspaces/{workspace_id}/translate`。

- [ ] **Step 4: pytest PASS**

```bash
cd backend && pytest tests/test_doc_translate_api.py -v
```

- [ ] **Step 5: Commit**

---

## Task 10: 前端 API 与路由迁移

**Files:**
- Create: `minerva-ui/src/api/translate.ts`
- Modify: `minerva-ui/src/app/router.tsx`
- Modify: `minerva-ui/src/app/layout/AppLayout.tsx`
- Modify: `minerva-ui/src/app/layout/AppBreadcrumb.tsx`
- Delete: `minerva-ui/src/features/doc-translate/`

- [ ] **Step 1: `api/translate.ts`**

类型：`DocTranslateJobListItem`, `DocTranslateJobDetail`, `DocTranslateSegment`, `DocTranslateJobListOut`。

函数：

- `createTranslateJob(workspaceId, FormData)`
- `listTranslateJobs(workspaceId, { limit, cursor })`
- `getTranslateJob`, `listTranslateJobSegments`, `getTranslateJobDownloadUrl`, `deleteTranslateJob`

- [ ] **Step 2: 路由 `/app/translate`**

```tsx
import { TranslatePage } from '@/features/translate'
// { path: 'translate', element: <TranslatePage /> }
// 删除 doc-translate 路由与 import
```

`AppLayout`：`SUB_DOC_TRANSLATE` 点击 `nav('/app/translate')`；`menuKeyForPath` 匹配 `/app/translate`；`contentScrollStyleForPath` 对 `/app/translate` 复用 agents chat 样式。

- [ ] **Step 3: 删除 doc-translate 目录**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(ui): add translate API client and /app/translate route"
```

---

## Task 11: TranslatePage UI

**Files:**
- Create: `minerva-ui/src/features/translate/TranslatePage.tsx`
- Create: `minerva-ui/src/features/translate/TranslatePage.css`
- Create: `minerva-ui/src/features/translate/translateJobUi.ts`
- Create: `minerva-ui/src/features/translate/index.ts`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: 布局骨架（复制 AgentsPage 结构）**

类名 `translate-page` / `__sider` / `__main` / `__scroll`；左侧 `useInfiniteQuery` 拉 jobs；右侧分「无选中」与「有选中」。

- [ ] **Step 2: 上传区**

- `Upload.Dragger` `accept=".docx,.pdf,.txt,.md,.csv,.xlsx"`
- 源/目标语言 `Select`（首期静态选项：`zh-CN`,`en`,`ja` 等；i18n label）
- 模型 `Select`：`listModelProviders` 过滤 `model_type === 'translate' && enabled && endpoint_url && has_api_key`
- 提交 `createTranslateJob` 后 `setSelectedJobId`

- [ ] **Step 3: 对照区 + 轮询**

`useQuery` job + segments，`refetchInterval: selected && !terminal ? 3000 : false`。

两列：`source_text` | `translated_text`（pending 显示 `t('translate.segmentPending')`）。

顶栏：`Progress`、`Tag` status、下载链接触发 `getTranslateJobDownloadUrl`（`SUCCESS`）。

删除：`Popconfirm` + `deleteTranslateJob`（遵守 minerva-conventions §4）。

- [ ] **Step 4: i18n 键**

`translate.newTask`, `translate.history`, `translate.sourceLang`, `translate.targetLang`, `translate.selectModel`, `translate.uploadHint`, `translate.compareTitle`, `translate.download`, `translate.segmentPending`, `translate.status.*`, `translate.deleteJob`, `translate.deleteConfirm`。

- [ ] **Step 5: 手动冒烟**

登录 → 文档翻译 → 上传 txt → 观察侧栏与对照列 → 下载。

- [ ] **Step 6: Commit**

---

## Task 12: 字典数据与文档收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-05-20-document-translate-design.md` — 状态改为「已实现」并注明计划路径
- （可选）种子 SQL 或迁移说明：`MODEL_TYPE` 增加 `translate` 项

- [ ] **Step 1: 确认工作区字典**

在「系统设置 → 字典」为 `MODEL_TYPE` 增加 code `translate`（显示名「翻译」）；语言字典 `TRANSLATE_LANG`（若实现动态 Select 则加项，否则文档注明静态列表）。

- [ ] **Step 2: 回填 spec 状态**

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: mark document-translate spec implemented"
```

---

## Spec 覆盖自检

| Spec 章节 | 任务 |
|-----------|------|
| §2 目录 `app/translate` / `features/translate` | Task 1–11 |
| §3 表名 job/segment | Task 1 |
| §4 Celery 单流水线 | Task 7–8 |
| §5 六格式策略 | Task 3–5 |
| §5.3 OCR 扫描 PDF | Task 5–6 |
| §6 API | Task 9 |
| §7 UI 对照+轮询 | Task 10–11 |
| §8 删除无级联 | Task 2, 9 |
| §11 环境变量 | Task 8 |
| 模型 translate | Task 7, 9, 11 |
| 语言每任务选择 | Task 9, 11 |

无 TBD；无「similar to Task X」省略实现。

---

## 执行方式

计划已保存至 `docs/superpowers/plans/2026-05-20-document-translate.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 按 Task 派发子代理，任务间你做审查，迭代快  
2. **Inline Execution** — 本会话用 executing-plans 按 Task 批量执行并在检查点暂停

你更希望用哪一种？回复 `1` 或 `2`（或「开始实现」）即可。
