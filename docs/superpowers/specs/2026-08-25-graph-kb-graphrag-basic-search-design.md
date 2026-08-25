# GraphKB：GraphRAG Basic Search（统一 mode=`basic`）

**状态：** 已实现  
**日期：** 2026-08-25  
**类型：** 行为扩展（查询模式）  
**关联：** [2026-08-23-graph-kb-graphrag-lightrag-design.md](./2026-08-23-graph-kb-graphrag-lightrag-design.md)

**Minerva 约定：** 改行为前对文档、改完回填；环境变量若变动须同步 `.env.example` / `.env.dev`（本改动未新增主 API 环境变量）。

---

## 1. 目标

为 GraphRAG 引擎接入 Microsoft GraphRAG 的 **Basic Search**（基于 text units 的向量 RAG），并在 Minerva 统一问答 API 中以新模式 **`basic`** 暴露。

**不**复用 `naive`：`naive` 仍仅 LightRAG；GraphRAG 请求 `naive` 继续 400。

---

## 2. 模式映射（以本文件为准，覆盖旧 spec §7.1）

| 统一 `mode` | GraphRAG | LightRAG |
|-------------|----------|----------|
| `local` | Local Search | local |
| `global` | Global Search | global |
| `hybrid` | 降级为 Global（首期不变） | hybrid |
| `naive` | **400** `graph_kb.invalid_mode` | naive |
| **`basic`** | **Basic Search** | **400** `graph_kb.invalid_mode` |

HTTP 错误补充：

| HTTP | 条件 |
|------|------|
| 400 | GraphRAG + `naive`；LightRAG + `basic`；未知 `mode` |
| 409 | `indexing_status` 不是 `completed` |
| 503 | Worker 不可达 |

---

## 3. 实现范围

### 3.1 主 API（`backend/app/graph_kb`）

- `domain/constants.py`：`QUERY_BASIC = "basic"`，加入 `QUERY_MODES`
- `engine/modes.py`：`map_query_mode` — GraphRAG 拒 `naive`；LightRAG 拒 `basic`
- `POST .../graph-kbs/{id}/query`：无新字段；`mode` 可收 `basic`；`top_k` 下发 Worker

### 3.2 GraphRAG Worker（`backend/workers/graph-kb-graphrag`）

- `store.py`：仍拒 `naive`；`mode=basic` → `_run_basic_search`（优先 `graphrag.api.basic_search`，否则 `BasicSearch` 类）
- FakeStore：`basic` 返回 `fake:...`（200）

### 3.3 前端

- GraphRAG：`local` / `global` / `hybrid` / `basic`
- LightRAG：`local` / `global` / `hybrid` / `naive`
- i18n：`graphKb.qa.mode.basic`

### 3.4 非目标

- 不新增 DRIFT；citations 首期可为空数组

---

## 5. 实现对照（以代码为准，2026-08-25）

| 条目 | 代码位置 | 备注 |
|------|----------|------|
| `QUERY_BASIC` / `map_query_mode` | `domain/constants.py`；`engine/modes.py` | 单测 `tests/test_graph_kb_engine_client.py` |
| GraphRAG Basic Search | `workers/graph-kb-graphrag/app/store.py` `_run_basic_search` | Fake 路径接受 `basic` |
| 前端按引擎选项 | `frontend/.../qa/GraphKbQaPage.tsx` `qaModesForEngine` | en/zh-CN `graphKb.qa.mode.basic` |

---

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-25 | 初稿：统一 `basic`；GraphRAG Basic Search；`naive` 仅 LightRAG |
| 2026-08-25 | 已实现并回填 §5 |
