# 规则库「概览」统计仪表盘 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前工作空间的 `rule_base` 提供只读聚合接口（规则总数 + 三个维度非空 distinct codes）；前端在 `RulesOverviewPage` 展示四个 KPI 与按维度分项列表，`code→名称` 使用字典 **`RULE_ENG_SUBJECT_DOC`**（与规则列表同源：`fetchDictByCode` / `buildCodeNameMap`）。

**Architecture:** 后端在既有 **`backend/app/rule`** 分层内追加：`repository` 内四条聚合查询（总条数 + 三列 `trim` 后非空的 `DISTINCT`）；`rule_base_service` 组装返回；`api/schemas.py` 增加响应模型；`router.py` 增加 **`GET .../overview-stats`**（置于 `/{rule_id}` 之前非强制，但推荐写在 patch/delete 之前以便阅读顺序一致）。前端：`ruleBase.ts` 增加 `getRuleBaseOverviewStats`；页面内 **`useQuery` ×2**（或 `useQueries`）并行拉取 stats 与字典；分项渲染复用 `buildCodeNameMap` 与「名称 (code)」格式。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, pytest+httpx；React 18, TanStack Query, Ant Design 6, react-i18next。

**设计依据:** `docs/superpowers/specs/2026-04-28-rules-overview-dashboard-design.md`

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/app/rule/infrastructure/repository.py` | 新增 `overview_stats_for_workspace`，四条查询 |
| `backend/app/rule/service/rule_base_service.py` | 新增 `get_rule_base_overview_stats`，调仓储 |
| `backend/app/rule/api/schemas.py` | 新增 `RuleBaseOverviewStatsOut` |
| `backend/app/rule/api/router.py` | `GET /overview-stats`，`Depends` 与列表一致 |
| `backend/tests/test_rule_base_api.py`（或新建 `test_rule_overview_stats_api.py`） | HTTP 集成测试：多行规则 + 空码 + 断言 JSON |
| `minerva-ui/src/api/ruleBase.ts` | `getRuleBaseOverviewStats`、`RuleBaseOverviewStats` 类型 |
| `minerva-ui/src/features/rules/RulesOverviewPage.tsx` | KPI 卡片 + 三个分项列表、loading/空态 |
| `minerva-ui/src/features/rules/RulesOverviewPage.css`（可选） | 若需与 `RulesManagementPage` 对齐的间距/卡片样式 |
| `minerva-ui/src/i18n/locales/zh-CN.json`、`en.json` | 概览 KPI/分项标题/空列表提示 |

---

## Task 1: 后端 — 仓储聚合

**Files:**

- Modify: `backend/app/rule/infrastructure/repository.py`

- [ ] **Step 1: 编写函数签名与契约**

在 `repository.py` 增加异步函数（名称可微调，一处引用即可）：

```python
# overview_stats_for_workspace(session, *, workspace_id: uuid.UUID)
# 返回: tuple[int, list[str], list[str], list[str]]
#   - rule_count: COUNT(*) WHERE workspace_id = :ws
#   - engineering_codes: DISTINCT trim(engineering_code) WHERE 非 NULL 且 trim 后非空，ORDER BY 1 ASC
#   - subject_codes: 同上列 subject_code
#   - document_type_codes: 同上列 document_type
```

使用 `sqlalchemy`：`select(func.count()).select_from(RuleBase).where(RuleBase.workspace_id == workspace_id)` 得 `rule_count`。

非空条件（三列共用模式，替换 `COLUMN`）：

```python
and_(
    RuleBase.workspace_id == workspace_id,
    COLUMN.isnot(None),
    func.trim(COLUMN) != "",
)
```

Distinct 列表（示例为 `engineering_code`）：

```python
stmt = (
    select(func.trim(RuleBase.engineering_code))
    .where(
        RuleBase.workspace_id == workspace_id,
        RuleBase.engineering_code.isnot(None),
        func.trim(RuleBase.engineering_code) != "",
    )
    .distinct()
    .order_by(func.trim(RuleBase.engineering_code))
)
result = await session.execute(stmt)
engineering_codes = [row[0] for row in result.all()]
```

对 `subject_code`、`document_type` 复制列名并各执行一次 `execute`。

- [ ] **Step 2: 本地静态检查**

Run: `cd backend && python -c "from app.rule.infrastructure import repository as r; print('ok')"`  
Expected: `ok`（若在项目根需 `PYTHONPATH=backend` 或 `uv run`，与仓库惯例一致）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/rule/infrastructure/repository.py
git commit -m "feat(rule): repository overview stats aggregates"
```

---

## Task 2: 后端 — Service + Schema

**Files:**

- Modify: `backend/app/rule/service/rule_base_service.py`
- Modify: `backend/app/rule/api/schemas.py`

- [ ] **Step 1: Pydantic 模型**

在 `schemas.py` 末尾增加：

```python
class RuleBaseOverviewStatsOut(BaseModel):
    rule_count: int = Field(ge=0)
    engineering_codes: list[str] = Field(default_factory=list)
    subject_codes: list[str] = Field(default_factory=list)
    document_type_codes: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Service 函数**

在 `rule_base_service.py` 增加：

```python
async def get_rule_base_overview_stats(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> tuple[int, list[str], list[str], list[str]]:
    return await repo.overview_stats_for_workspace(session, workspace_id=workspace_id)
```

确保 `repo` 已从 `app.rule.infrastructure import repository as repo`，若仓储函数名不同则改为实际名称。

- [ ] **Step 3: Commit**

```bash
git add backend/app/rule/api/schemas.py backend/app/rule/service/rule_base_service.py
git commit -m "feat(rule): overview stats service and schema"
```

---

## Task 3: 后端 — 路由

**Files:**

- Modify: `backend/app/rule/api/router.py`

- [ ] **Step 1: 导入与注册**

从 `schemas` 导入 `RuleBaseOverviewStatsOut`。在 `@router.get("")` **之后**、`@router.post("")` **之前**（或紧邻列表路由）添加：

```python
@router.get(
    "/overview-stats",
    response_model=RuleBaseOverviewStatsOut,
)
async def get_rule_base_overview_stats(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RuleBaseOverviewStatsOut:
    rule_count, eng, sub, doc = await svc.get_rule_base_overview_stats(
        session, workspace_id=workspace_id
    )
    return RuleBaseOverviewStatsOut(
        rule_count=rule_count,
        engineering_codes=eng,
        subject_codes=sub,
        document_type_codes=doc,
    )
```

若 `svc.get_rule_base_overview_stats` 直接返回 `RuleBaseOverviewStatsOut`，可简化为一次 `return await svc...`。

- [ ] **Step 2: 手动请求（可选）**

启动应用后（与项目 README 一致）：`GET /workspaces/{wid}/rule-base/overview-stats` + Bearer token，期望 200 与 JSON 结构。

- [ ] **Step 3: Commit**

```bash
git add backend/app/rule/api/router.py
git commit -m "feat(rule): GET overview-stats endpoint"
```

---

## Task 4: 后端 — 集成测试（TDD 顺序：先红后绿）

**Files:**

- Modify: `backend/tests/test_rule_base_api.py`（推荐与现有 CRUD 测试同文件，复用注册/ token 模式）

- [ ] **Step 1: 编写失败测试**

在文件中新增 `test_rule_base_overview_stats`：流程与 `test_rule_base_crud_and_isolation` 类似——`register` 得 `token1`、`workspace1`、`h1`；**POST 三条** `rule-base` 记录，body 在 `_sample_rule_json()` 基础上扩展，例如：

- 规则 A：`engineering_code: "E1"`, `subject_code: "S1"`, `document_type: "D1"`
- 规则 B：与 A 相同三码（验重）
- 规则 C：`engineering_code: "E2"`, `subject_code: null`, `document_type: ""` 或省略（验空不计入对应 distinct）

必填字段：`review_section`, `review_object`, `review_rules`, `review_result`, `status`, `sequence_number`。

然后：

```python
r = await ac.get(f"/workspaces/{workspace1}/rule-base/overview-stats", headers=h1)
assert r.status_code == 200
data = r.json()
assert data["rule_count"] == 3
assert data["engineering_codes"] == ["E1", "E2"]  # 有序
assert "S1" in data["subject_codes"] and len(data["subject_codes"]) == 1
# document_type 按你的 fixtures 断言 distinct 列表
```

非成员：`GET` 同一 URL + `h2`，期望 **403**（与 `rule-base` 列表行为一致）。

- [ ] **Step 2: 运行测试直至失败**

Run:

```bash
cd backend && pytest tests/test_rule_base_api.py::test_rule_base_overview_stats -v
```

Expected（实现前）: FAIL（`404` 或函数未定义）。

- [ ] **Step 3: 实现 Tasks 1–3 后重跑**

Expected: PASS

Run full rule tests:

```bash
cd backend && pytest tests/test_rule_base_api.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_rule_base_api.py
git commit -m "test(rule): overview-stats API"
```

---

## Task 5: 前端 — API 封装

**Files:**

- Modify: `minerva-ui/src/api/ruleBase.ts`

- [ ] **Step 1: 类型与函数**

```typescript
export type RuleBaseOverviewStats = {
  rule_count: number
  engineering_codes: string[]
  subject_codes: string[]
  document_type_codes: string[]
}

export function getRuleBaseOverviewStats(workspaceId: string) {
  return apiJson<RuleBaseOverviewStats>(
    `/workspaces/${workspaceId}/rule-base/overview-stats`,
  )
}
```

（若已有 `ruleBasePath`，用其拼接 `/overview-stats`。）

- [ ] **Step 2: Commit**

```bash
git add minerva-ui/src/api/ruleBase.ts
git commit -m "feat(ui): rule base overview stats API client"
```

---

## Task 6: 前端 — `RulesOverviewPage` 页面

**Files:**

- Modify: `minerva-ui/src/features/rules/RulesOverviewPage.tsx`
- Create（可选）: `minerva-ui/src/features/rules/RulesOverviewPage.css`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`、`en.json`

- [ ] **Step 1: 数据**

- `const { workspaceId } = useAuth()`
- `useQuery`：`queryKey: ['ruleBaseOverviewStats', workspaceId]`，`queryFn: () => getRuleBaseOverviewStats(workspaceId!)`，`enabled: Boolean(workspaceId)`
- 第二查询复用 **`useDictItemTree(ENG_SUBJECT_DOC_DICT_CODE)`**（与 `RulesManagementPage.tsx` 一致），从 `data.flat` 取 `buildCodeNameMap(flat)`（或 `fetchDictByCode` 返回的 `flat`——以 hook 返回结构为准；若 hook 只给 `itemTree`，则 `flattenDictItemTree` + `buildCodeNameMap`）

- [ ] **Step 2: 展示组件**

- 顶部 `Row` + `Col`（`span={6}`）：四张 **`Card`** 或 **`Statistic`**，标题 i18n：`rules.overview.kpiEngineering`、`kpiSubject`、`kpiDocType`、`kpiRules`（键名可在 JSON 中最终确定）；数字：`stats.engineering_codes.length` 等 + `stats.rule_count`。
- 下方三个 **`Card`**：`List`/`Tag` 渲染 `engineering_codes.map(code => ({ title: label(code), description: code }))`，其中 `label`：`const name = map.get(code); return name ? `${name} (${code})` : code`。
- `Spin` 包裹至 stats 与 dict 均就绪（或分别 skeleton）；错误 `Result`/`Alert` + `ApiError` 消息。

- [ ] **Step 3: i18n**

在 `zh-CN.json` / `en.json` 增加 KPI 标题、分项标题（工程/专业/文档类型）、「暂无数据」删除 `placeholders.rulesOverview` 或改为简短说明。

- [ ] **Step 4: 类型检查**

Run:

```bash
cd minerva-ui && npm run build
```

Expected: 无 TS 错误。

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/rules/RulesOverviewPage.tsx minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
# 若有 CSS：
# git add minerva-ui/src/features/rules/RulesOverviewPage.css
git commit -m "feat(ui): rules overview dashboard with KPI and scope lists"
```

---

## Spec 对照自检（计划作者填写）

| 规格要求 | 对应任务 |
|----------|----------|
| `GET .../overview-stats`，成员鉴权 | Task 3 |
| `rule_count` + 三列 distinct codes，trim 非空 | Task 1 |
| 排序 UTF-8 升序 | Task 1 `order_by` |
| 前端 KPI + 分项，字典名称 | Task 5–6 |
| 测试含多规则与空码 | Task 4 |

**Placeholder 扫描:** 本计划无 TBD；测试断言中的具体 `engineering_codes` 顺序依赖 fixtures，实现测试时以规格「升序」为准调整期望值。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-04-28-rules-overview-dashboard.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks in this session using checkpoints. **REQUIRED SUB-SKILL:** `superpowers:executing-plans`.

Which approach would you like to use?
