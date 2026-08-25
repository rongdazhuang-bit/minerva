# GraphRAG Basic Search (`mode=basic`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unified query mode `basic` that maps to GraphRAG Basic Search; keep `naive` LightRAG-only; update API validation, Worker, frontend, docs, and tests.

**Architecture:** Extend `QUERY_MODES` with `basic`. `map_query_mode` rejects GraphRAG+`naive` and LightRAG+`basic`. GraphRAG Worker runs Basic Search on `basic` (FakeStore accepts it). Frontend `qaModesForEngine` returns engine-specific option lists.

**Tech Stack:** FastAPI GraphKB API, GraphRAG Worker (`graphrag.api.basic_search` when available), React QA page, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-graph-kb-graphrag-basic-search-design.md`
- Do not reuse `naive` for GraphRAG; do not add DRIFT
- Citations for basic may stay `[]` (same as current GraphRAG query)
- Comment every new/changed class/method per Minerva code-comments skill
- After code: backfill `2026-08-23` design §7.1 and this feature’s §5 实现对照
- Commits only if user asks

---

### Task 1: Main API mode validation

**Files:**
- Modify: `backend/app/graph_kb/domain/constants.py`
- Modify: `backend/app/graph_kb/engine/modes.py`
- Modify: `backend/tests/test_graph_kb_engine_client.py`

**Interfaces:**
- Produces: `QUERY_BASIC = "basic"`; `map_query_mode(engine, mode) -> str` with engine-specific 400s

- [ ] **Step 1: Write failing tests**

In `backend/tests/test_graph_kb_engine_client.py`, replace/extend:

```python
def test_graphrag_rejects_naive() -> None:
    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_GRAPHRAG, QUERY_NAIVE)
    assert exc.value.status_code == 400


def test_graphrag_accepts_basic() -> None:
    assert map_query_mode(ENGINE_GRAPHRAG, "basic") == "basic"


def test_lightrag_rejects_basic() -> None:
    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_LIGHTRAG, "basic")
    assert exc.value.status_code == 400
    assert exc.value.code == "graph_kb.invalid_mode"
```

Import `QUERY_NAIVE` if needed; use string `"basic"` until constant exists, or import `QUERY_BASIC` after Step 3.

- [ ] **Step 2: Run tests — expect fail**

```bash
cd backend && APP_ENV=test .venv/bin/python -m pytest tests/test_graph_kb_engine_client.py::test_graphrag_accepts_basic tests/test_graph_kb_engine_client.py::test_lightrag_rejects_basic -q
```

Expected: FAIL (`basic` not in `QUERY_MODES` or LightRAG accepts it).

- [ ] **Step 3: Implement constants + modes**

`constants.py`:

```python
QUERY_BASIC = "basic"
QUERY_MODES = frozenset(
    {QUERY_LOCAL, QUERY_GLOBAL, QUERY_HYBRID, QUERY_NAIVE, QUERY_BASIC}
)
```

`modes.py`:

```python
from app.graph_kb.domain.constants import (
    ENGINE_GRAPHRAG,
    ENGINE_LIGHTRAG,
    QUERY_BASIC,
    QUERY_MODES,
    QUERY_NAIVE,
)

def map_query_mode(engine: str, mode: str) -> str:
    """Validate unified mode; GraphRAG rejects naive; LightRAG rejects basic."""

    if mode not in QUERY_MODES:
        raise AppError("graph_kb.invalid_mode", "不支持的检索模式。", 400)
    if engine == ENGINE_GRAPHRAG and mode == QUERY_NAIVE:
        raise AppError("graph_kb.invalid_mode", "GraphRAG 不支持 naive 模式。", 400)
    if engine == ENGINE_LIGHTRAG and mode == QUERY_BASIC:
        raise AppError("graph_kb.invalid_mode", "LightRAG 不支持 basic 模式。", 400)
    return mode
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && APP_ENV=test .venv/bin/python -m pytest tests/test_graph_kb_engine_client.py -q
```

Expected: PASS (all tests in file).

---

### Task 2: GraphRAG Worker accepts `basic`

**Files:**
- Modify: `backend/workers/graph-kb-graphrag/app/store.py`
- Modify: `backend/workers/graph-kb-graphrag/tests/test_root.py`

**Interfaces:**
- Consumes: HTTP `mode` string including `basic`
- Produces: FakeStore `query(..., mode="basic")` → 200 `fake:...`; real store `basic` → Basic Search

- [ ] **Step 1: Failing test — Fake `basic` is 200**

In `test_root.py` `test_fake_index_writes_fake_json_and_delete_removes_root` (or sibling), after global query assert, add:

```python
    basic = client.post(
        "/query",
        json={
            "workspace_id": str(wid),
            "graph_id": str(gid),
            "engine": "graphrag",
            "query": "q",
            "mode": "basic",
            "top_k": 5,
        },
        headers=_AUTH,
    )
    assert basic.status_code == 200
    assert basic.json()["answer"].startswith("fake:")
```

Keep existing `mode=naive` → 400 assertion.

- [ ] **Step 2: Run worker test — expect fail if Fake still rejects unknown paths**

Fake currently only rejects naive; `basic` may already 200. If already green, still implement real-store branch.

```bash
cd backend/workers/graph-kb-graphrag && .venv/bin/python -m pytest tests/test_root.py -q -k fake_index
```

- [ ] **Step 3: Implement store query branches**

FakeStore `query`: keep `_reject_naive`; allow `basic` (no extra check).

`GraphRAGStore.query`:

```python
        _reject_naive(mode)
        normalized = (mode or "global").strip().lower()
        root = self._root(workspace_id, graph_id)
        if normalized == "basic":
            answer = await self._run_basic_search(root, query, top_k=top_k)
        elif normalized in ("global", "hybrid"):
            ...
        elif normalized == "local":
            ...
        else:
            raise HTTPException(...)
```

Add `_run_basic_search(self, root, query, *, top_k)`:
1. Try `from graphrag.api import basic_search` + load config/text_units from root (parquet under `output/`).
2. Pass `k=top_k` when API allows.
3. On ImportError / missing artifacts: raise HTTP 502 with clear detail, or fall back to `_run_search(BasicSearch, ...)` if class import works.
4. Prefer best-effort matching existing `_run_search` resilience.

- [ ] **Step 4: Run worker tests**

```bash
cd backend/workers/graph-kb-graphrag && .venv/bin/python -m pytest tests/ -q
```

Expected: PASS.

---

### Task 3: Frontend QA modes + i18n

**Files:**
- Modify: `frontend/src/features/graph-kb/qa/GraphKbQaPage.tsx`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh-CN.json`

- [ ] **Step 1: Update `qaModesForEngine`**

```tsx
const ALL_QA_MODES = ['local', 'global', 'hybrid', 'naive', 'basic'] as const

/** Modes allowed for an engine: GraphRAG gets basic; LightRAG gets naive. */
export function qaModesForEngine(engine: string | undefined): readonly string[] {
  if (engine === ENGINE_GRAPHRAG) {
    return ALL_QA_MODES.filter((mode) => mode !== 'naive')
  }
  return ALL_QA_MODES.filter((mode) => mode !== 'basic')
}
```

Update file/header comments accordingly.

- [ ] **Step 2: i18n keys**

```json
"graphKb.qa.mode.basic": "Basic"
```

```json
"graphKb.qa.mode.basic": "Basic"
```

(zh-CN may use `"Basic"` or `"基础检索"` — prefer `"Basic"` for parity with Local/Global, or `"基础检索"` if product prefers Chinese.)

- [ ] **Step 3: Manual sanity** — TypeScript compiles; mode Select options change when engine is graphrag vs lightrag.

---

### Task 4: Docs backfill

**Files:**
- Modify: `docs/superpowers/specs/2026-08-23-graph-kb-graphrag-lightrag-design.md` (§7.1 mode table, 400 row, §11, §12)
- Modify: `docs/superpowers/specs/2026-08-25-graph-kb-graphrag-basic-search-design.md` (status + §5 实现对照)

- [ ] **Step 1: Update §7.1 table** — add `basic` row; GraphRAG naive still 400; LightRAG basic 400
- [ ] **Step 2: Fill 实现对照 paths** in 2026-08-25 design; status → 已实现
- [ ] **Step 3: Revision log lines dated 2026-08-25

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| `QUERY_BASIC` + map_query_mode rules | 1 |
| GraphRAG Worker Basic Search / Fake | 2 |
| Frontend engine-specific modes + i18n | 3 |
| Design doc backfill | 4 |
| LightRAG Worker change | N/A (API gate) |

---

## Execution

Plan saved. Prefer **inline execution** in this session (small scope: 4 tasks).
