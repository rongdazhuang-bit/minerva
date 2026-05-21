# 文档翻译页 UI 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将文档翻译主界面改为「顶部筛选 + 表格列表」，上传与段落对照分别放入 Modal / 全屏 Modal；列表 API 支持分页与文件名/状态/时间筛选；后端翻译流水线不变。

**Architecture:** 后端在 `translate/infrastructure/repository.py` 新增 filtered offset 查询，替换 `GET /jobs` 的 cursor 响应为 `{ items, total }`（对齐 `file_ocr.list_ocr_files`）。前端 `TranslatePage` 参照 `FileOcrTaskPage` 单页结构，复用现有 `createTranslateJob`、详情轮询与对照网格 CSS。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest + httpx AsyncClient, React 18, Ant Design, TanStack Query, i18next.

**设计依据:** `docs/superpowers/specs/2026-05-21-document-translate-ui-refresh-design.md`

---

## 文件结构（将修改）

### 后端

- Modify: `backend/app/translate/infrastructure/repository.py` — 新增 `list_doc_translate_jobs_filtered`
- Modify: `backend/app/translate/api/schemas.py` — `DocTranslateJobListOut` 改为 `items` + `total`
- Modify: `backend/app/translate/api/router.py` — `list_translate_jobs` 查询参数与实现
- Create: `backend/tests/test_doc_translate_list_api.py` — 列表分页与筛选
- Keep: `backend/tests/test_doc_translate_repository_cursor.py` — cursor 编解码保留（不再被列表路由使用）

### 前端

- Modify: `minerva-ui/src/api/translate.ts` — 列表类型与 query 参数
- Modify: `minerva-ui/src/features/translate/TranslatePage.tsx` — 表格 + 双 Modal
- Modify: `minerva-ui/src/features/translate/TranslatePage.css` — 移除侧栏样式，增加表格页布局
- Modify: `minerva-ui/src/app/layout/AppLayout.tsx` — `/app/translate` 不再使用 agents 零 padding
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`
- Modify: `docs/superpowers/specs/2026-05-20-document-translate-design.md` — §6.2、§7 回填

---

## Task 1: 列表 Repository（分页 + 筛选）

**Files:**
- Modify: `backend/app/translate/infrastructure/repository.py`
- Create: `backend/tests/test_doc_translate_list_api.py`（本 Task 仅写 repository 相关断言的占位，完整 API 在 Task 2）

- [ ] **Step 1: 在 `repository.py` 末尾新增函数**

```python
async def list_doc_translate_jobs_filtered(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    file_name: str | None = None,
    status: str | None = None,
    create_at_start: datetime | None = None,
    create_at_end: datetime | None = None,
) -> tuple[list[DocTranslateJob], int]:
    """Return jobs newest-first with offset pagination and optional filters."""

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    sort_ts = func.coalesce(DocTranslateJob.update_at, DocTranslateJob.create_at)
    stmt = select(DocTranslateJob).where(DocTranslateJob.workspace_id == workspace_id)
    if file_name is not None and file_name.strip() != "":
        stmt = stmt.where(DocTranslateJob.file_name.ilike(f"%{file_name.strip()}%"))
    if status is not None and status.strip() != "":
        stmt = stmt.where(DocTranslateJob.status == status.strip())
    if create_at_start is not None:
        stmt = stmt.where(DocTranslateJob.create_at >= create_at_start)
    if create_at_end is not None:
        stmt = stmt.where(DocTranslateJob.create_at <= create_at_end)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(await session.scalar(total_stmt) or 0)
    rows = (
        await session.execute(
            stmt.order_by(desc(sort_ts), desc(DocTranslateJob.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total
```

- [ ] **Step 2: 确认 import**

文件顶部已有 `select`, `func`, `desc`, `or_`, `and_`；若无 `datetime` 从 `datetime` 导入。

- [ ] **Step 3: 运行现有测试无回归**

```bash
cd backend && pytest tests/test_doc_translate_repository_cursor.py tests/test_doc_translate_models.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add backend/app/translate/infrastructure/repository.py
git commit -m "feat(translate): add filtered offset job list repository"
```

---

## Task 2: 列表 API（Schema + Router + 测试）

**Files:**
- Modify: `backend/app/translate/api/schemas.py`
- Modify: `backend/app/translate/api/router.py`
- Create: `backend/tests/test_doc_translate_list_api.py`

- [ ] **Step 1: 更新 Schema**

`DocTranslateJobListOut`：

```python
class DocTranslateJobListOut(BaseModel):
    """Offset-paginated job list with optional filters."""

    items: list[DocTranslateJobListItemOut]
    total: int = 0
```

删除 `jobs` / `next_cursor` 字段。`DocTranslateJobListItemOut` 的 docstring 改为「表格一行」。

- [ ] **Step 2: 写失败 API 测试（列表结构）**

`backend/tests/test_doc_translate_list_api.py` 参照 `test_file_ocr_api.py`：注册工作区用户、`POST` 创建 job（可 mock `create_job_from_upload` 或最小 multipart），再 `GET /jobs?page=1&page_size=10`，断言：

```python
async def test_list_translate_jobs_returns_items_and_total() -> None:
    # ... setup workspace + auth headers ...
    r = await client.get(f"/workspaces/{ws_id}/translate/jobs?page=1&page_size=10", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
```

另增 `test_list_translate_jobs_filters_by_status`：创建两条不同 status 的 job（或 patch DB），`?status=SUCCESS` 仅返回 SUCCESS。

- [ ] **Step 3: 运行测试确认失败**

```bash
cd backend && pytest tests/test_doc_translate_list_api.py -v
```

Expected: FAIL（响应仍含 `jobs` 或 422）。

- [ ] **Step 4: 重写 `list_translate_jobs` 路由**

```python
from app.pagination import DEFAULT_PAGE_SIZE

@router.get("/jobs", response_model=DocTranslateJobListOut)
async def list_translate_jobs(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    file_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    create_at_start: datetime | None = Query(default=None),
    create_at_end: datetime | None = Query(default=None),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateJobListOut:
    """List translation jobs with offset pagination and optional filters."""

    rows, total = await translate_repo.list_doc_translate_jobs_filtered(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        file_name=file_name,
        status=status,
        create_at_start=create_at_start,
        create_at_end=create_at_end,
    )
    return DocTranslateJobListOut(
        items=[_job_list_item(r) for r in rows],
        total=total,
    )
```

将现有 `DocTranslateJobListItemOut(...)` 构造提取为 `_job_list_item(r: DocTranslateJob) -> DocTranslateJobListItemOut` 避免重复。移除 `cursor`/`limit`/`next_cursor`/`invalid_cursor` 分支。删除 router 对 `DOC_TRANSLATE_LIST_DEFAULT_LIMIT` 的 import（若不再使用）。

- [ ] **Step 5: 运行测试**

```bash
cd backend && pytest tests/test_doc_translate_list_api.py -v
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/translate/api/schemas.py backend/app/translate/api/router.py backend/tests/test_doc_translate_list_api.py
git commit -m "feat(translate): paginated filtered job list API"
```

---

## Task 3: 前端 API 客户端

**Files:**
- Modify: `minerva-ui/src/api/translate.ts`

- [ ] **Step 1: 替换列表类型与函数**

```typescript
export type DocTranslateJobListOut = {
  items: DocTranslateJobListItem[]
  total: number
}

export type DocTranslateJobListParams = {
  page?: number
  page_size?: number
  file_name?: string
  status?: string
  create_at_start?: string
  create_at_end?: string
}

export function listTranslateJobs(workspaceId: string, params?: DocTranslateJobListParams) {
  const sp = new URLSearchParams()
  if (params?.file_name?.trim()) sp.set('file_name', params.file_name.trim())
  if (params?.status?.trim()) sp.set('status', params.status.trim())
  if (params?.create_at_start?.trim()) sp.set('create_at_start', params.create_at_start.trim())
  if (params?.create_at_end?.trim()) sp.set('create_at_end', params.create_at_end.trim())
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  const suffix = q ? `/jobs?${q}` : '/jobs'
  return apiJson<DocTranslateJobListOut>(`/workspaces/${workspaceId}/translate${suffix}`)
}
```

- [ ] **Step 2: 类型检查**

```bash
cd minerva-ui && npm run build
```

Expected: 仅 `TranslatePage.tsx` 因旧字段报错（下一步修复）。

- [ ] **Step 3: Commit**

```bash
git add minerva-ui/src/api/translate.ts
git commit -m "feat(ui): translate job list API params and response shape"
```

---

## Task 4: i18n 与 AppLayout

**Files:**
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`
- Modify: `minerva-ui/src/app/layout/AppLayout.tsx`

- [ ] **Step 1: 新增 i18n 键（zh-CN / en 同步）**

```json
"translate.filter.fileName": "文件名",
"translate.filter.fileNamePh": "模糊匹配",
"translate.filter.status": "状态",
"translate.filter.createRange": "创建时间",
"translate.newJob": "新建翻译",
"translate.table.fileName": "文件名",
"translate.table.lang": "语言",
"translate.table.status": "状态",
"translate.table.progress": "进度",
"translate.table.createAt": "创建时间",
"translate.table.actions": "操作",
"translate.table.view": "查看",
"translate.uploadModal.title": "上传文档并翻译",
"translate.detailModal.title": "翻译详情"
```

英文对应翻译。保留现有 `translate.status.*`、`translate.lang.*` 等键。

- [ ] **Step 2: 调整 AppLayout padding**

在 `contentScrollStyleForPath` 中，将条件改为 **仅** `pathname.startsWith('/app/agents/chat')` 使用 agents 特殊 padding；**移除** `/app/translate` 分支，使翻译页使用默认 `contentScrollStyle`（`padding: 20`）。

- [ ] **Step 3: Commit**

```bash
git add minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json minerva-ui/src/app/layout/AppLayout.tsx
git commit -m "feat(ui): translate page i18n and standard layout padding"
```

---

## Task 5: TranslatePage — 表格与筛选

**Files:**
- Modify: `minerva-ui/src/features/translate/TranslatePage.tsx`
- Modify: `minerva-ui/src/features/translate/TranslatePage.css`

- [ ] **Step 1: 替换页面状态与列表查询**

删除：`selectedJobId`（侧栏选中）、`useInfiniteQuery`、`handleShowUpload`、整个 `<aside className="translate-page__sider">`。

新增：

```typescript
const [filterForm] = Form.useForm()
const [appliedFilters, setAppliedFilters] = useState<DocTranslateJobListParams>({})
const [page, setPage] = useState(1)
const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
const tableWrapRef = useRef<HTMLDivElement>(null)
const [tableBodyScrollY, setTableBodyScrollY] = useState(420)
```

`listQuery = useQuery({ queryKey: ['translate-jobs', workspaceId, page, pageSize, appliedFilters], queryFn: () => listTranslateJobs(workspaceId!, { page, page_size: pageSize, ...appliedFilters }) })`

`onSearch`：`setAppliedFilters(valuesToParams(values)); setPage(1)`。`onReset`：`filterForm.resetFields(); setAppliedFilters({}); setPage(1)`。

日期范围：与 `FileOcrTaskPage` 相同，将 `Dayjs[]` 转为 ISO 字符串写入 `create_at_start` / `create_at_end`。

- [ ] **Step 2: 实现筛选 Form + Table 骨架**

页面根节点改为单栏，例如：

```tsx
<div className="translate-page translate-page--table">
  <Card size="small" variant="borderless" className="translate-page__card">
    <Form form={filterForm} layout="inline" onFinish={onSearch} className="translate-page__filter">
      {/* file_name Input allowClear, status Select allowClear, create_range RangePicker */}
      <Button htmlType="submit" type="primary">{t('rules.search')}</Button>
      <Button onClick={onReset}>{t('rules.resetFilter')}</Button>
      <Button type="dashed" icon={<FileAddOutlined />} onClick={() => setUploadOpen(true)}>
        {t('translate.newJob')}
      </Button>
    </Form>
    <div ref={tableWrapRef} className="translate-page__table-wrap">
      <Table columns={columns} dataSource={listQuery.data?.items ?? []} ... />
    </div>
  </Card>
</div>
```

`columns` 含：文件名、语言（`source_lang → target_lang`）、状态 Tag、进度、创建时间、操作（查看/删除/下载）。`rowKey="id"`，`onRow` 点击设置 `detailJobId`。

`useLayoutEffect` 计算 `tableBodyScrollY`（复制 OCR 页的 resize 逻辑，常量 gutter 可本地定义为 `48`）。

分页：`total: listQuery.data?.total ?? 0`，`pageSizeOptions: [10,20,50,100]`。

- [ ] **Step 3: 更新 CSS**

删除 `translate-page__sider*`、`translate-page__job-row*`、`translate-page__upload-center*` 规则。

新增：

```css
.translate-page--table {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 0;
}
.translate-page__card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.translate-page__filter { margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.translate-page__table-wrap { flex: 1; min-height: 0; }
```

保留 `__compare-grid`、`__segment-row`、`__toolbar` 供详情 Modal。

- [ ] **Step 4: 手动验证列表**

启动前后端，打开 `/app/translate`，确认表格与筛选、分页正常。

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/translate/TranslatePage.tsx minerva-ui/src/features/translate/TranslatePage.css
git commit -m "feat(ui): translate jobs table with filters"
```

---

## Task 6: 上传 Modal 与详情全屏 Modal

**Files:**
- Modify: `minerva-ui/src/features/translate/TranslatePage.tsx`
- Modify: `minerva-ui/src/features/translate/TranslatePage.css`

- [ ] **Step 1: 上传 Modal**

状态：`uploadOpen`, `uploadFile`, `sourceLang`, `targetLang`, `modelId`, `submitting`（可从主区迁移）。

```tsx
<Modal
  title={t('translate.uploadModal.title')}
  open={uploadOpen}
  onCancel={() => { setUploadOpen(false); setUploadFile(null) }}
  destroyOnHidden
  footer={null}
  width={560}
>
  {/* 原 Form：Dragger + 语言 + 模型 + Alert + 提交 Button */}
</Modal>
```

`handleSubmit` 成功后：`setUploadOpen(false)`、`setUploadFile(null)`、`invalidateQueries(['translate-jobs'])`、`setDetailJobId(out.id)`。

- [ ] **Step 2: 详情全屏 Modal**

状态：`detailJobId: string | null`。

```tsx
<Modal
  className="translate-page__detail-modal"
  title={/* 文件名 + Tag + Progress + 下载 */}
  open={detailJobId != null}
  onCancel={() => setDetailJobId(null)}
  footer={null}
  width="100%"
  style={{ top: 0, paddingBottom: 0, maxWidth: '100%' }}
  styles={{
    body: { height: 'calc(100vh - 110px)', overflow: 'auto', padding: '12px 20px' },
  }}
  destroyOnHidden
>
  {/* jobQuery + segmentsQuery；迁移原 compare-grid + FAILED Alert */}
</Modal>
```

`jobQuery` / `segmentsQuery` 的 `enabled` 改为 `Boolean(workspaceId && detailJobId)`，`queryKey` 含 `detailJobId`。轮询逻辑不变（非终态 3000ms）。

操作列「查看」：`setDetailJobId(record.id)`。

- [ ] **Step 3: 详情 Modal CSS**

```css
.translate-page__detail-modal .ant-modal-content {
  height: 100vh;
  display: flex;
  flex-direction: column;
}
.translate-page__detail-modal .translate-page__compare-grid {
  min-height: 0;
}
```

- [ ] **Step 4: 端到端手动验证**

1. 新建翻译 → 自动打开详情 Modal → 轮询至完成  
2. 关闭详情 → 表格有该行  
3. SUCCESS 下载、Popconfirm 删除  
4. 筛选文件名/状态/日期

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/translate/TranslatePage.tsx minerva-ui/src/features/translate/TranslatePage.css
git commit -m "feat(ui): translate upload and fullscreen detail modals"
```

---

## Task 7: 清理与文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-05-20-document-translate-design.md`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`（删除未引用键，可选）

- [ ] **Step 1: 回填原设计文档 §7**

将 §7.1–7.4 更新为表格 + 上传 Modal + 全屏详情 Modal；§6.2 改为 offset 分页 + 筛选参数表；§12 增加「2026-05-21 UI 重构见 `2026-05-21-document-translate-ui-refresh-design.md`」。

- [ ] **Step 2: 移除未使用的 i18n 键**

若代码中不再引用，删除 `translate.history`、`translate.loadMore`、`translate.newTranslate`（或保留别名到 `translate.newJob`）。

- [ ] **Step 3: 全量回归**

```bash
cd backend && pytest tests/test_doc_translate_list_api.py tests/test_doc_translate_repository_cursor.py tests/test_doc_translate_strategies_txt_md_csv.py -v
cd minerva-ui && npm run build
```

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-20-document-translate-design.md minerva-ui/src/i18n/locales/*.json
git commit -m "docs: align document-translate spec with table UI refresh"
```

---

## Spec 自检（计划覆盖）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| GET /jobs 分页 + A/B/C 筛选 | Task 1–2 |
| 表格列与操作 | Task 5 |
| 上传 Modal，逻辑不变 | Task 6 |
| 全屏详情 Modal + 轮询对照 | Task 6 |
| 上传成功自动开详情 | Task 6 Step 1 |
| AppLayout padding | Task 4 |
| i18n | Task 4、7 |
| 回填 2026-05-20 spec | Task 7 |
| POST/segments/download/delete 不变 | 无任务（不修改） |

---

## 执行方式

计划已保存。可选：

1. **Subagent-Driven（推荐）** — 每 Task 派发子代理，任务间做代码审查  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，检查点分批汇报  

请告知选择 **1** 或 **2**（或「开始实现」），即从 Task 1 动手。
