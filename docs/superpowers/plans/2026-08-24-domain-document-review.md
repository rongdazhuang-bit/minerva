# 专业领域文档校审系统 Implementation Plan（P0–P3）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付插件化文档校审底座与六条产品线：错别字、规则、合同、法律文书、以文审文、全文一致性；支持 md/txt/excel/doc/docx/pdf；doc/docx/pdf 写回批注；内容包种子入库与发布锁定；任务级可观察性。

**Architecture:** 统一 `DocumentIR` + `ReviewProfile` 组装 Stage（L1–L5）；Job 创建时锁定 `pack_release_id`；Celery 单任务流水线 `PARSING → REVIEWING → ANNOTATING|EXPORT → SUCCESS`；Observability 贯穿 event/metric/trace；前端六入口共用 Job API。

**Tech Stack:** FastAPI, SQLAlchemy async, Celery, Pydantic v2, python-docx, pymupdf, openpyxl, React 18, Ant Design, TanStack Query, i18next。LLM 经可 mock 的 `ReviewLlmGateway`。

**设计依据:** `docs/superpowers/specs/2026-08-24-domain-document-review-design.md`

**范围说明:**
- **Tasks 1–14 = P0+P1（必须按序做完，可独立上线 typo + rule）**
- **Tasks 15–18 = P2（contract / legal / consistency）**
- **Tasks 19–21 = P3（text2text / excel / doc 转换）**
- 执行时可在 Task 14 后设检查点再开 P2。

## Global Constraints

- 数据库表 **禁止** `FOREIGN KEY` / `ON DELETE CASCADE`；删除在 service 层显式清理。
- 批注仅 **doc / docx / pdf**；md/txt/excel 出报告（excel 结果 sheet）。
- doc：**先转 docx** 再批注；首期交付 docx。
- 首期 **不** 自动改写正文。
- 内容包：种子 + publish + Job 锁定 release；在线编辑 draft **不做**（本计划内）。
- 可观察性：事件时间线 + 指标骨架 + 任务详情四块面板为 **P0/P1 必做**。
- 规则包为空的 `rule` 任务创建返回 **422**。
- 单块 LLM 失败可跳过；失败块比例 **> 30%** 则整单 `FAILED`。
- 环境变量变更须同步 `backend/.env.example` 与 `backend/.env.dev`。
- 前端二次确认只用 Ant Design `Popconfirm`。
- 主内容区布局：圆角 4px、外边距 3px、页内滚动（见 `frontend/docs/LAYOUT.md`）。

---

## 文件结构（将创建 / 将修改）

### 后端新建 `backend/app/review/`

```text
backend/app/review/
  __init__.py
  domain/
    constants.py
    profiles.py                 # ReviewProfile 静态定义
    dto.py                      # DocumentIR, Block, Anchor, Finding, …
    db/models.py                # review_* + content_* ORM
  infrastructure/
    repository.py
  observability/
    handle.py                   # ObservabilityHandle
    metrics.py                  # 计数器/直方图注册（可先 no-op + 内存）
  packs/
    seed_loader.py
    release_service.py
  ingest/
    registry.py
    parsers/
      txt.py, md.py, docx_parser.py, pdf_parser.py
      # P3: xlsx.py, xls.py, doc_bridge.py
  llm/
    gateway.py
    schemas_typo.py
    schemas_rule.py
    # P2+: schemas_domain.py, schemas_compare.py, schemas_consistency.py
  engine/
    runtime.py
    merge.py
    stages/
      base.py
      typo_l1.py
      rule_l2.py
      # P2: domain_l3.py, consistency_l5.py
      # P3: compare_l4.py
  annotate/
    docx_comments.py
    pdf_annotations.py
  export/
    report.py
  service/
    job_service.py
    job_delete.py
    run_pipeline.py
  task/
    run_job.py
  api/
    deps.py, schemas.py, router.py
```

### 种子与 SQL

- Create: `backend/app/review/content_seeds/manifest.json`
- Create: `backend/app/review/content_seeds/typo_terms/v1/pack.yaml`
- Create: `backend/app/review/content_seeds/rule_demo/v1/pack.yaml`
- Create: `backend/app/review/content_seeds/contract/v1/pack.yaml`（P2）
- Create: `backend/app/review/content_seeds/legal/v1/pack.yaml`（P2）
- Create: `backend/app/review/content_seeds/compare/v1/pack.yaml`（P3）
- Create: `backend/app/review/content_seeds/consistency/v1/pack.yaml`（P2）
- Modify: `backend/sql/schema_postgresql.sql`

### 后端修改

- `backend/app/core/infrastructure/db/bootstrap.py` — import review models
- `backend/app/core/api/router.py` — include review router
- `backend/app/celery_app.py` — import `app.review.task.run_job`
- `backend/app/config.py` + `.env.example` + `.env.dev`
- `backend/pyproject.toml` — 确认 `python-docx`、`pymupdf`、`openpyxl`（P3）

### 前端

- Create: `frontend/src/api/review.ts`
- Modify: `frontend/src/features/smart-review/TextProofreadingPage.tsx` — typo 产品线
- Create: `frontend/src/features/smart-review/RuleReviewPage.tsx` — 或扩展路由
- Create: `frontend/src/features/smart-review/ReviewJobDetail.tsx` — 四块可观察面板 + findings
- Create: `frontend/src/features/smart-review/reviewJobUi.ts`
- Modify: `frontend/src/app/router.tsx`、i18n
- P2/P3: 合同/法律/一致性/以文审文页替换占位

### 测试

- `backend/tests/test_review_*.py`（按 Task 列出）

---

# 里程碑 P0+P1

### Task 1: 常量、DTO 与 ORM / SQL

**Files:**
- Create: `backend/app/review/domain/constants.py`
- Create: `backend/app/review/domain/dto.py`
- Create: `backend/app/review/domain/db/models.py`
- Create: `backend/app/review/domain/db/__init__.py`
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Test: `backend/tests/test_review_models.py`

**Interfaces:**
- Produces: ORM `ReviewJob`, `ReviewJobFile`, `ReviewFinding`, `ReviewJobEvent`, `ContentPack`, `ContentClause`, `ContentChecklistItem`, `ContentRuleItem`, `ContentPackRelease`
- Produces DTO: `DocumentIR`, `Block`, `Anchor`, `Finding`, `Evidence`, `EvidenceHit`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_review_models.py
from app.review.domain.db.models import (
    ContentPack,
    ContentPackRelease,
    ReviewFinding,
    ReviewJob,
    ReviewJobEvent,
    ReviewJobFile,
)


def test_review_job_tablename() -> None:
    assert ReviewJob.__tablename__ == "review_job"


def test_no_foreign_key_on_review_job_file() -> None:
    for col in ReviewJobFile.__table__.columns:
        assert col.foreign_keys == set()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_models.py -v
```

Expected: `ModuleNotFoundError` or import failure.

- [ ] **Step 3: Write minimal implementation**

`constants.py` 至少包含：

```python
REVIEW_RUN_TASK_NAME = "review.run_job"
REVIEW_ALLOWED_EXTS_P1 = frozenset({"txt", "md", "docx", "pdf"})
REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_PARSING = "PARSING"
REVIEW_STATUS_REVIEWING = "REVIEWING"
REVIEW_STATUS_ANNOTATING = "ANNOTATING"
REVIEW_STATUS_SUCCESS = "SUCCESS"
REVIEW_STATUS_FAILED = "FAILED"
REVIEW_STATUS_CANCELLED = "CANCELLED"
REVIEW_LLM_FAIL_BLOCK_RATIO = 0.30
REVIEW_PROFILES_P1 = frozenset({"typo", "rule"})
```

`dto.py`：用 Pydantic v2 模型实现 spec §4 的 `DocumentIR` / `Block` / `Anchor`（discriminated union）/ `Finding`。

`models.py`：列对齐 spec §8.2 与 §10；UUID 列 **无** `ForeignKey`；为 `workspace_id`、`job_id`、`pack_id` 建普通 Index。

`schema_postgresql.sql`：追加对应 `CREATE TABLE`（文件头禁止 FK）。

`bootstrap._import_models` 追加：

```python
import app.review.domain.db.models  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review backend/sql/schema_postgresql.sql backend/app/core/infrastructure/db/bootstrap.py backend/tests/test_review_models.py
git commit -m "feat(review): add review and content pack schema"
```

---

### Task 2: ReviewProfile 注册表

**Files:**
- Create: `backend/app/review/domain/profiles.py`
- Test: `backend/tests/test_review_profiles.py`

**Interfaces:**
- Produces: `get_profile(profile_id: str) -> ReviewProfile`
- Produces: `ReviewProfile` dataclass/Pydantic：`id`, `display_name`, `inputs`, `stages`, `packs`, `annotation`, `llm`

- [ ] **Step 1: Write the failing test**

```python
from app.review.domain.profiles import get_profile


def test_typo_profile_stages() -> None:
    p = get_profile("typo")
    assert p.stages == ["typo_l1"]
    assert p.inputs.arity == 1


def test_rule_profile_requires_rule_pack_key() -> None:
    p = get_profile("rule")
    assert p.stages == ["rule_l2"]
    assert "rule_pack_ids" in (p.packs or {})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_profiles.py -v
```

Expected: FAIL import or missing function.

- [ ] **Step 3: Write minimal implementation**

实现 `typo` 与 `rule` 两个 Profile（P2/P3 Profile 可先占位 raise `KeyError` 或一并注册但 Stage 未实现时由 runtime 报错）。`annotation.enabled_formats = ("doc", "docx", "pdf")`，`write_mode = "always"`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_profiles.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/domain/profiles.py backend/tests/test_review_profiles.py
git commit -m "feat(review): register typo and rule profiles"
```

---

### Task 3: ObservabilityHandle

**Files:**
- Create: `backend/app/review/observability/handle.py`
- Create: `backend/app/review/observability/metrics.py`
- Test: `backend/tests/test_review_observability.py`

**Interfaces:**
- Produces: `ObservabilityHandle.emit(event_type: str, *, level: str = "info", stage_id: str | None = None, duration_ms: int | None = None, **attrs) -> None`
- Produces: `ObservabilityHandle.inc(metric: str, **labels) -> None`
- Produces: `ObservabilityHandle.observe(metric: str, value: float, **labels) -> None`
- Consumes: repository method `insert_job_event(...)`（可先用 in-memory list 注入，Task 4 再接 DB）

- [ ] **Step 1: Write the failing test**

```python
from app.review.observability.handle import ObservabilityHandle


def test_emit_appends_event() -> None:
    sink: list[dict] = []
    obs = ObservabilityHandle(job_id="j1", trace_id="t1", sink=sink.append)
    obs.emit("stage.started", stage_id="typo_l1")
    assert sink[0]["event_type"] == "stage.started"
    assert sink[0]["job_id"] == "j1"
    assert sink[0]["trace_id"] == "t1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_observability.py::test_emit_appends_event -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`ObservabilityHandle` 将事件写成 dict（含 `ts` ISO）；`metrics.py` 提供进程内 `Counter` dict（后续可换 Prometheus）。`payload_mode` 默认截断 quote 至 200 字符。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/observability backend/tests/test_review_observability.py
git commit -m "feat(review): add observability handle and in-memory metrics"
```

---

### Task 4: Repository（Job / Finding / Event / Content）

**Files:**
- Create: `backend/app/review/infrastructure/repository.py`
- Test: `backend/tests/test_review_repository.py`

**Interfaces:**
- Produces: `create_job`, `get_job`, `list_jobs`, `update_job_status`, `add_file`, `add_findings`, `list_findings`, `insert_job_event`, `list_job_events`, `create_pack_with_items`, `publish_pack`, `get_release`, `resolve_published_release(pack_code: str) -> ContentPackRelease`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.review.infrastructure.repository import resolve_published_release_code


def test_resolve_published_release_code_helper() -> None:
    # pure helper used by seed/job lock — returns None if missing
    assert resolve_published_release_code({}) is None
```

（若仓库用异步 session，改为 async 集成测：创建 pack → publish → resolve 非空。）

推荐集成测骨架：

```python
@pytest.mark.asyncio
async def test_publish_and_resolve(session_factory):
    # insert draft pack + rule item → publish → resolve_published_release("rule_demo") is not None
    ...
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_repository.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

实现上述 repository 方法；`publish_pack` 将当前 draft 项序列化为 JSON 写入对象存储或 `snapshot_json` 文本列（P0 可用 DB `Text` 存 snapshot，避免强依赖 S3）；写 `content_pack_release` 并 `version += 1`，`status=published`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_repository.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/infrastructure/repository.py backend/tests/test_review_repository.py
git commit -m "feat(review): add job and content pack repository"
```

---

### Task 5: 内容种子加载（typo_terms + rule_demo）

**Files:**
- Create: `backend/app/review/content_seeds/manifest.json`
- Create: `backend/app/review/content_seeds/typo_terms/v1/pack.yaml`
- Create: `backend/app/review/content_seeds/rule_demo/v1/pack.yaml`
- Create: `backend/app/review/packs/seed_loader.py`
- Create: `backend/app/review/packs/release_service.py`
- Test: `backend/tests/test_review_seed_loader.py`

**Interfaces:**
- Produces: `apply_seeds(session, *, strategy: Literal["skip_if_exists","merge_additive","replace_draft","publish_new_version"] = "skip_if_exists") -> list[SeedResult]`
- Produces: `lock_releases_for_profile(session, profile_id: str, pack_codes: list[str]) -> list[UUID]`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from app.review.packs.seed_loader import load_manifest


def test_manifest_lists_typo_and_rule() -> None:
    codes = {p["code"] for p in load_manifest()}
    assert "typo_terms" in codes
    assert "rule_demo" in codes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_seed_loader.py::test_manifest_lists_typo_and_rule -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`manifest.json`：

```json
{
  "packs": [
    {"code": "typo_terms", "path": "typo_terms/v1/pack.yaml", "kind": "typo"},
    {"code": "rule_demo", "path": "rule_demo/v1/pack.yaml", "kind": "rule"}
  ]
}
```

`rule_demo` 至少 2 条规则（1 hard 正则、1 soft prompt）。`typo_terms` 含术语白名单列表。`apply_seeds` 默认 `skip_if_exists`；成功后 `emit` 逻辑上等价于 `content_seed.applied`（可由调用方打 event）。

提供 CLI 或 FastAPI admin：`POST /workspaces/{id}/review/content-packs/seed`（Task 12 挂路由）。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_seed_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/content_seeds backend/app/review/packs backend/tests/test_review_seed_loader.py
git commit -m "feat(review): add content pack seed loader for typo and rule"
```

---

### Task 6: 解析器 txt / md / docx / pdf → DocumentIR

**Files:**
- Create: `backend/app/review/ingest/parsers/txt.py`
- Create: `backend/app/review/ingest/parsers/md.py`
- Create: `backend/app/review/ingest/parsers/docx_parser.py`
- Create: `backend/app/review/ingest/parsers/pdf_parser.py`
- Create: `backend/app/review/ingest/registry.py`
- Test: `backend/tests/test_review_parsers.py`
- Test fixtures: `backend/tests/fixtures/review/sample.txt`, `sample.md`, `sample.docx`, `sample.pdf`

**Interfaces:**
- Produces: `parse_document(path: Path, *, file_name: str, format: str) -> DocumentIR`
- Consumes: DTO from Task 1

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from app.review.ingest.registry import parse_document


def test_parse_txt_blocks(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("第一行\n第二行\n", encoding="utf-8")
    ir = parse_document(p, file_name="a.txt", format="txt")
    assert len(ir.blocks) >= 2
    assert ir.blocks[0].anchor.type == "text"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_parsers.py::test_parse_txt_blocks -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

- txt/md：按行或空行分段，`Anchor(type="text", line_start, line_end)`。
- docx：`python-docx` 段落索引；`Anchor(type="docx", paragraph_index=i)`。
- pdf：`pymupdf` 按页抽文本块；无文字层时 raise 明确错误（OCR 留 P3/后续，本任务不自动 OCR）。
- registry：按 format 分发；未知格式 `ValueError`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_parsers.py -v
```

Expected: PASS（含 docx/pdf fixture 各至少 1 测）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/ingest backend/tests/test_review_parsers.py backend/tests/fixtures/review
git commit -m "feat(review): parse txt md docx pdf into DocumentIR"
```

---

### Task 7: LLM Gateway（可 mock）

**Files:**
- Create: `backend/app/review/llm/gateway.py`
- Create: `backend/app/review/llm/schemas_typo.py`
- Create: `backend/app/review/llm/schemas_rule.py`
- Test: `backend/tests/test_review_llm_gateway.py`

**Interfaces:**
- Produces: `ReviewLlmGateway.complete(*, messages: list[dict], response_schema: dict, model_policy: str, stage_id: str) -> tuple[dict, LlmUsage]`
- Produces: `LlmUsage(prompt_tokens: int, completion_tokens: int, model: str)`
- Schema 失败最多重试 2 次，仍失败 raise `LlmSchemaError`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.review.llm.gateway import FakeReviewLlmGateway, LlmSchemaError


@pytest.mark.asyncio
async def test_fake_gateway_returns_json() -> None:
    gw = FakeReviewLlmGateway(fixed={"items": []})
    data, usage = await gw.complete(
        messages=[{"role": "user", "content": "x"}],
        response_schema={"type": "object"},
        model_policy="small",
        stage_id="typo_l1",
    )
    assert data == {"items": []}
    assert usage.prompt_tokens >= 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_llm_gateway.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

实现 `FakeReviewLlmGateway` + `OpenAICompatibleReviewLlmGateway`（调用现有 `app.llm` 或 httpx）；单元测试默认只用 Fake。`schemas_typo.py` / `schemas_rule.py` 导出 JSON Schema 常量。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_llm_gateway.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/llm backend/tests/test_review_llm_gateway.py
git commit -m "feat(review): add mockable LLM gateway and schemas"
```

---

### Task 8: Stage `typo_l1` + Finding merge

**Files:**
- Create: `backend/app/review/engine/stages/base.py`
- Create: `backend/app/review/engine/stages/typo_l1.py`
- Create: `backend/app/review/engine/merge.py`
- Test: `backend/tests/test_review_stage_typo.py`
- Test: `backend/tests/test_review_merge.py`

**Interfaces:**
- Produces: `class Stage(Protocol): async def run(self, ctx: ReviewContext) -> list[Finding]`
- Produces: `TypoL1Stage`
- Produces: `merge_findings(findings: list[Finding]) -> list[Finding]`
- Consumes: `ReviewContext`（含 `docs`, `llm`, `obs`, `packs`）

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.review.domain.dto import Block, DocumentIR, TextAnchor
from app.review.engine.stages.typo_l1 import TypoL1Stage
from app.review.llm.gateway import FakeReviewLlmGateway


@pytest.mark.asyncio
async def test_typo_stage_emits_finding():
    ir = DocumentIR(
        doc_id="d1",
        file_name="a.txt",
        format="txt",
        blocks=[Block(block_id="b0", text="这里有错别字", kind="paragraph", anchor=TextAnchor(type="text", line_start=0, line_end=0), order=0)],
    )
    gw = FakeReviewLlmGateway(
        fixed={"items": [{"block_id": "b0", "wrong_span": "错别字", "suggest": "错别字", "reason": "demo", "severity": "warn"}]}
    )
    # build ReviewContext with docs={"main": ir}, llm=gw, packs whitelist empty
    stage = TypoL1Stage()
    findings = await stage.run(ctx)
    assert len(findings) == 1
    assert findings[0].category == "typo"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_stage_typo.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`TypoL1Stage`：分块调用 LLM；映射 `block_id`；白名单术语命中则丢弃；每条 finding 后 `obs.emit("finding.emitted", ...)`。`merge_findings`：同一 `block_id` + 相同 `message` 去重，severity 取更高者（定义序 `info < warn < error < critical`）。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_stage_typo.py tests/test_review_merge.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/engine backend/tests/test_review_stage_typo.py backend/tests/test_review_merge.py
git commit -m "feat(review): implement typo_l1 stage and finding merge"
```

---

### Task 9: Stage `rule_l2`

**Files:**
- Create: `backend/app/review/engine/stages/rule_l2.py`
- Test: `backend/tests/test_review_stage_rule.py`

**Interfaces:**
- Produces: `RuleL2Stage`
- Hard rules：`match_mode=hard` 时对全文/块跑 `re.search(pattern)`；命中即 Finding，`rule_id=code`
- Soft rules：相关块 top-k（P1：简单关键词重叠）+ LLM `pass|fail|uncertain`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_hard_rule_hits():
    # IR 含禁用词「机密」；rule hard pattern 机密 → 1 finding, rule_id set
    ...
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_stage_rule.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

从 `ctx.packs["rule"]` 快照读 `content_rule_item` 列表；无规则则 Stage 开始即 raise `RulePackEmptyError`（Job 创建层也应 422）。uncertain → severity `warn`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_stage_rule.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/engine/stages/rule_l2.py backend/tests/test_review_stage_rule.py
git commit -m "feat(review): implement rule_l2 hard and soft checks"
```

---

### Task 10: Engine runtime

**Files:**
- Create: `backend/app/review/engine/runtime.py`
- Test: `backend/tests/test_review_runtime.py`

**Interfaces:**
- Produces: `async def run_review(ctx: ReviewContext) -> list[Finding]`
- 按 `profile.stages` 顺序实例化 Stage；`stage.started/done/failed` 事件；累计 LLM 失败块比例超阈则 raise

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_runtime_runs_typo_only():
    # profile typo → only typo_l1 called (spy)
    ...
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_runtime.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Stage 注册表：`{"typo_l1": TypoL1Stage, "rule_l2": RuleL2Stage}`。返回 `merge_findings(all)`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_runtime.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/engine/runtime.py backend/tests/test_review_runtime.py
git commit -m "feat(review): add profile-driven review runtime"
```

---

### Task 11: 批注写回（docx / pdf）与报告导出（txt/md）

**Files:**
- Create: `backend/app/review/annotate/docx_comments.py`
- Create: `backend/app/review/annotate/pdf_annotations.py`
- Create: `backend/app/review/export/report.py`
- Test: `backend/tests/test_review_annotate_docx.py`
- Test: `backend/tests/test_review_export_report.py`

**Interfaces:**
- Produces: `write_docx_comments(source: Path, findings: list[Finding], ir: DocumentIR, out: Path) -> AnnotateStats`
- Produces: `write_pdf_annotations(...) -> AnnotateStats`
- Produces: `export_findings_report(findings, *, format: Literal["json","csv"]) -> bytes`
- `AnnotateStats(written: int, unanchored: int, failed: int)`

- [ ] **Step 1: Write the failing test**

```python
def test_docx_comment_count(tmp_path):
    # minimal docx + 1 finding with paragraph_index 0 → output has >=1 comment
    ...
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_annotate_docx.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

docx：python-docx comments API 或 OOXML 关系写入；作者固定 `Minerva Review`；正文用 template `[severity] message\n建议: suggestion`。  
pdf：pymupdf 在页上加 highlight + info 注解。  
定位失败：`unanchored += 1`，不抛。  
txt/md：JSON 数组报告。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_annotate_docx.py tests/test_review_export_report.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/review/annotate backend/app/review/export backend/tests/test_review_annotate_docx.py backend/tests/test_review_export_report.py
git commit -m "feat(review): write docx/pdf annotations and text reports"
```

---

### Task 12: Job 流水线 + Celery + API

**Files:**
- Create: `backend/app/review/service/run_pipeline.py`
- Create: `backend/app/review/service/job_service.py`
- Create: `backend/app/review/service/job_delete.py`
- Create: `backend/app/review/task/run_job.py`
- Create: `backend/app/review/api/schemas.py`
- Create: `backend/app/review/api/router.py`
- Create: `backend/app/review/api/deps.py`
- Modify: `backend/app/core/api/router.py`
- Modify: `backend/app/celery_app.py`
- Modify: `backend/app/config.py`, `.env.example`, `.env.dev`
- Test: `backend/tests/test_review_api.py`
- Test: `backend/tests/test_review_pipeline.py`

**Interfaces:**
- API（workspace 作用域，与 translate 一致）：
  - `POST /workspaces/{workspace_id}/review/jobs`
  - `GET /workspaces/{workspace_id}/review/jobs`
  - `GET /workspaces/{workspace_id}/review/jobs/{job_id}`
  - `GET .../findings`、`.../events`、`.../download`
  - `POST .../cancel`、`POST .../retry-annotate`、`DELETE ...`
  - `GET /workspaces/{workspace_id}/review/content-packs`
  - `POST /workspaces/{workspace_id}/review/content-packs/seed`
- `create_job`：校验 profile ∈ P1；`rule` 时 resolve `rule_demo` release，空则 422；写入 `pack_release_ids`；上传源文件到存储；enqueue Celery
- `run_pipeline`：状态机 + obs 事件；失败写 `failed_stage`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_create_rule_job_without_pack_returns_422(client):
    # no seed applied → 422
    ...
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_review_api.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

按 Interfaces 实现；删除顺序：events → findings → files（含对象）→ job。配置项示例：`review_max_file_bytes`、`review_poll_hint_seconds=3`。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_review_api.py tests/test_review_pipeline.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/review backend/app/core/api/router.py backend/app/celery_app.py backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_review_api.py backend/tests/test_review_pipeline.py
git commit -m "feat(review): add job pipeline, celery task, and REST API"
```

---

### Task 13: 前端 — typo / rule 页 + 可观察详情

**Files:**
- Create: `frontend/src/api/review.ts`
- Modify: `frontend/src/features/smart-review/TextProofreadingPage.tsx`
- Create: `frontend/src/features/smart-review/RuleReviewPage.tsx`
- Create: `frontend/src/features/smart-review/ReviewJobDetail.tsx`
- Create: `frontend/src/features/smart-review/ReviewJobList.tsx`
- Create: `frontend/src/features/smart-review/reviewJobUi.ts`
- Create: `frontend/src/features/smart-review/ReviewPages.css`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`, `en.json`
- Modify: `frontend/src/features/smart-review/index.ts`

**Interfaces:**
- `review.ts`：与 Task 12 API 一一对应的 client 函数
- 详情四块：进度+Stage、事件时间线、资源账单（token/次数/耗时）、产出摘要（severity / annotate stats / pack version）
- 轮询：任务非终态每 3s `GET job`

- [ ] **Step 1: Write the failing test（若前端无单测基建则改为手工检查清单）**

若仓库有 vitest：

```ts
import { formatReviewStatus } from './reviewJobUi'
expect(formatReviewStatus('REVIEWING')).toBeTruthy()
```

否则本 Task Step 1–2 记录为：打开页面前端类型检查。

```bash
cd frontend && npx tsc --noEmit
```

Expected: 在实现前因缺模块失败或既有基线；实现后无新增 error。

- [ ] **Step 2: Run check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Write minimal implementation**

- `/app/smart-review/text-proofreading` → profile=`typo`
- 新增或映射规则校审路由 → profile=`rule`（可用现有「以文审文」旁新菜单或临时挂在 text 页 Tab；**优先**新路由 `/app/smart-review/rule-review`，菜单 seed 可 P1 末尾补）
- 上传 `Upload.Dragger` accept `.txt,.md,.docx,.pdf`
- 删除任务用 `Popconfirm`
- 布局：`minerva-page-fill` / shell card 约定

- [ ] **Step 4: 浏览器验证**

1. 种子 API 或启动时 seed  
2. 上传 txt 跑 typo，详情见时间线与 findings  
3. 上传 docx 跑 rule，下载 annotated  
4. 取消与删除  

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/review.ts frontend/src/features/smart-review frontend/src/app/router.tsx frontend/src/i18n
git commit -m "feat(smart-review): typo and rule review UI with observability panel"
```

---

### Task 14: P0+P1 收尾 — 文档回填与回归

**Files:**
- Modify: `docs/superpowers/specs/2026-08-24-domain-document-review-design.md` — 状态与「实现对照」表
- Test: 跑全量 review 测试

- [ ] **Step 1: 跑回归**

```bash
cd backend && pytest tests/test_review_*.py -v
```

Expected: 全部 PASS。

- [ ] **Step 2: 回填 spec**

文首状态改为「P0+P1 已实现 / P2–P3 未做」；增加「实现对照」表：API、表名、删除顺序、代码路径。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-24-domain-document-review-design.md
git commit -m "docs(review): backfill P0/P1 implementation map"
```

**P0+P1 检查点：** typo + rule 可交付；内容种子与可观察性可用。以下为 P2/P3。

---

# 里程碑 P2（合同 / 法律 / 一致性）

### Task 15: 领域包种子 + `domain_l3` Stage

**Files:**
- Create: `backend/app/review/content_seeds/contract/v1/pack.yaml`
- Create: `backend/app/review/content_seeds/legal/v1/pack.yaml`
- Create: `backend/app/review/llm/schemas_domain.py`
- Create: `backend/app/review/engine/stages/domain_l3.py`
- Modify: `backend/app/review/domain/profiles.py` — `contract` / `legal`
- Modify: `manifest.json`
- Test: `backend/tests/test_review_stage_domain.py`

**Interfaces:**
- `DomainL3Stage(domain_pack_code: str)`：Phase A 抽取 `DocumentProfile`（JSON schema 来自 release）；Phase B 逐 checklist item → Finding（`checklist_item_id`）
- Profile：`stages=["domain_l3"]`，`packs.domain_pack_id` 指向 code

- [ ] **Step 1: Write failing test** — fake LLM 返回缺「管辖条款」→ 1 domain finding  
- [ ] **Step 2: Run — expect FAIL**  
- [ ] **Step 3: Implement seed + stage + profile**  
- [ ] **Step 4: pytest PASS**  
- [ ] **Step 5: Commit** `feat(review): add domain_l3 for contract and legal packs`

---

### Task 16: `consistency_l5` Stage

**Files:**
- Create: `backend/app/review/content_seeds/consistency/v1/pack.yaml`
- Create: `backend/app/review/engine/stages/consistency_l5.py`
- Create: `backend/app/review/llm/schemas_consistency.py`
- Modify: `profiles.py` — `consistency`；可选挂到 contract/legal 第二 stage
- Test: `backend/tests/test_review_stage_consistency.py`

**Interfaces:**
- 构建 `FactIndex`；同 key 多值 → Finding（`related` 双锚点）；可选 LLM 语义矛盾

- [ ] **Step 1–5:** TDD 同前；Commit `feat(review): add consistency_l5 stage`

---

### Task 17: P2 API / Pipeline 接线

**Files:**
- Modify: `constants.py` — `REVIEW_PROFILES` 含 contract/legal/consistency；扩展允许格式仍为 P1 集合
- Modify: `runtime.py` stage registry
- Modify: `job_service.py` — 锁定 domain/consistency releases
- Test: `backend/tests/test_review_api_p2.py`

- [ ] **Step 1–5:** 创建 contract job 需已 seed；Commit `feat(review): wire contract legal consistency jobs`

---

### Task 18: 前端合同 / 法律 / 一致性页

**Files:**
- Create/Modify smart-review 各 Page；router；i18n；菜单 seed（若需新菜单项）
- 复用 `ReviewJobList` / `ReviewJobDetail`

- [ ] **Step 1–5:** tsc + 浏览器三入口各跑一单；Commit `feat(smart-review): contract legal consistency pages`

---

# 里程碑 P3（以文审文 / Excel / doc）

### Task 19: `compare_l4` + 双文件上传

**Files:**
- Create: `backend/app/review/engine/stages/compare_l4.py`
- Create: `backend/app/review/content_seeds/compare/v1/pack.yaml`
- Create: `backend/app/review/llm/schemas_compare.py`
- Modify: `profiles.py` — `text2text`，`inputs.arity=2+`
- Modify: `job_service` / API — `role=main|reference` 多文件
- Modify: 前端以文审文页双上传槽
- Test: `backend/tests/test_review_stage_compare.py`

**Interfaces:**
- 对齐：条款号/标题启发式 + 可选 embedding（P3 可先纯启发式 + LLM 比对配对段）
- Finding：`evidence.primary=main`，`related=reference`；批注只写主文

- [ ] **Step 1–5:** TDD；Commit `feat(review): add text-to-text compare_l4`

---

### Task 20: Excel 解析与结果 sheet；doc→docx

**Files:**
- Create: `backend/app/review/ingest/parsers/xlsx.py`（及 xls 若环境支持）
- Create: `backend/app/review/ingest/parsers/doc_bridge.py` — LibreOffice/`soffice` 转 docx
- Modify: `export/report.py` — xlsx 增加「校审结果」sheet
- Modify: `constants.py` — 扩展 `REVIEW_ALLOWED_EXTS`
- Test: `backend/tests/test_review_parsers_excel.py`, `test_review_doc_bridge.py`

- [ ] **Step 1–5:** TDD；无 soffice 时 doc_bridge 测 skip；Commit `feat(review): excel parse/report and doc-to-docx bridge`

---

### Task 21: P3 收尾与全量回填

**Files:**
- Spec 实现对照更新为 P0–P3
- 全量 `pytest tests/test_review_*.py`
- 可选：扫描 PDF OCR bridge（若做，单独小任务；本计划默认 **不做** 自动 OCR，与 spec 非目标一致）

- [ ] **Step 1: 全量回归 PASS**  
- [ ] **Step 2: 回填 spec 状态「已实现」**  
- [ ] **Step 3: Commit** `docs(review): backfill full implementation map`

---

## Spec 覆盖自检

| Spec 要求 | Task |
|-----------|------|
| 插件化引擎 + Profile | 2, 10 |
| DocumentIR / Finding | 1, 6 |
| L1 typo / L2 rule | 8, 9 |
| L3 contract/legal | 15, 17, 18 |
| L4 text2text | 19 |
| L5 consistency | 16–18 |
| 格式 md/txt/docx/pdf | 6 |
| excel / doc 转换 | 20 |
| 批注 docx/pdf | 11 |
| 报告 txt/md/xlsx | 11, 20 |
| 内容种子 + release 锁定 | 5, 12 |
| 可观察性事件/指标/面板 | 3, 12, 13 |
| API / 删除无 FK | 4, 12 |
| 六产品线 UI | 13, 18, 19 |

**占位符扫描：** 无 TBD；P2/P3 步骤为压缩 TDD 循环但仍含文件与接口。  
**类型一致性：** `DocumentIR` / `Finding` / `ObservabilityHandle` / `pack_release_ids` 贯穿 Tasks 1–12。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-08-24-domain-document-review.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每个 Task 新开子代理，Task 间评审，迭代快  
2. **Inline Execution** — 本会话用 executing-plans 按批执行并设检查点  

**Which approach?**（建议从 Task 1 做到 Task 14 检查点后再开 P2。）
