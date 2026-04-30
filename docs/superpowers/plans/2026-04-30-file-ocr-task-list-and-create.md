# 文件OCR任务列表与新增流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `文件OCR > 任务列表` 交付可用的列表查询过滤与“选择OCR类型+上传文件”的两屏新增流程，完成 S3 上传后入库 `ocr_file` 任务（初始 `INIT`）。

**Architecture:** 采用“前后端一体直改”方案：后端继续在 `app/file_ocr` 垂直模块内扩展列表与创建接口，并调整 `ocr_file` 模型字段；前端在 `RulesFileOcrTasksPage` 实现筛选表格与两屏不可关闭弹窗，第二屏手动触发上传并展示进度，再调用创建接口入库。保持现有 S3 上传路由复用，不引入新子系统。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, React 18 + Ant Design, React Query, TypeScript, i18next.

**设计依据:** `docs/superpowers/specs/2026-04-30-file-ocr-task-list-design.md`

---

## 文件结构（将创建 / 将修改）

- `backend/sql/schema_postgresql.sql`：同步 `ocr_file` 字段（新增 `file_size/object_key/page_count`，删除 `file_uri`）。
- `backend/app/file_ocr/domain/db/models.py`：ORM 字段调整。
- `backend/app/file_ocr/api/schemas.py`：列表查询、分页、创建入参/出参模型。
- `backend/app/file_ocr/api/router.py`：新增列表接口、创建接口，保留概览统计接口。
- `backend/tests/test_file_ocr_api.py`（新建）：`file_ocr` API 集成测试。
- `minerva-ui/src/api/ocrFile.ts`：新增列表、创建、S3 上传（含进度）API 方法与类型。
- `minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx`：实现任务列表页、筛选、分页、两屏不可关闭弹窗、手动上传进度。
- `minerva-ui/src/features/file-ocr/RulesFileOcrPage.css`：任务列表与上传区域样式（含进度区域）。
- `minerva-ui/src/i18n/locales/zh-CN.json`：新增中文文案。
- `minerva-ui/src/i18n/locales/en.json`：新增英文文案。

---

## Task 1: 后端模型与Schema先红后绿

**Files:**
- Modify: `backend/app/file_ocr/domain/db/models.py`
- Modify: `backend/app/file_ocr/api/schemas.py`
- Create: `backend/tests/test_file_ocr_api.py`

- [ ] **Step 1: 写失败测试（模型与响应字段契约）**

在 `backend/tests/test_file_ocr_api.py` 添加最小契约测试：

```python
from app.file_ocr.api.schemas import OcrFileListItemOut


def test_ocr_file_list_item_schema_has_object_key_and_file_size() -> None:
    row = OcrFileListItemOut(
        id="00000000-0000-0000-0000-000000000000",
        workspace_id="00000000-0000-0000-0000-000000000000",
        file_name="a.pdf",
        ocr_type="PADDLE_OCR",
        status="INIT",
        file_size=123,
        object_key="ocr/file/a.pdf",
        page_count=None,
        create_at=None,
        update_at=None,
    )
    assert row.object_key == "ocr/file/a.pdf"
    assert row.file_size == 123
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_ocr_file_list_item_schema_has_object_key_and_file_size -v
```

Expected: FAIL（`OcrFileListItemOut` 不存在或缺字段）。

- [ ] **Step 3: 最小实现模型与schema**

`backend/app/file_ocr/domain/db/models.py` 更新核心字段：

```python
file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
file_size: Mapped[int | None] = mapped_column(nullable=True)
object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
ocr_type: Mapped[str] = mapped_column(String(16), nullable=False)
status: Mapped[str] = mapped_column(String(16), nullable=False)
page_count: Mapped[int | None] = mapped_column(nullable=True)
```

`backend/app/file_ocr/api/schemas.py` 增加列表项模型：

```python
class OcrFileListItemOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    file_name: str | None
    ocr_type: str
    status: str
    file_size: int | None = Field(default=None, ge=0)
    object_key: str
    page_count: int | None = Field(default=None, ge=0)
    create_at: datetime | None
    update_at: datetime | None
```

- [ ] **Step 4: 重跑测试确认通过**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_ocr_file_list_item_schema_has_object_key_and_file_size -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/file_ocr/domain/db/models.py backend/app/file_ocr/api/schemas.py backend/tests/test_file_ocr_api.py
git commit -m "feat(file-ocr): add new ocr_file fields and list schemas"
```

---

## Task 2: 后端任务列表查询（过滤+分页）

**Files:**
- Modify: `backend/app/file_ocr/api/router.py`
- Modify: `backend/app/file_ocr/api/schemas.py`
- Modify: `backend/tests/test_file_ocr_api.py`

- [ ] **Step 1: 写失败集成测试（过滤与分页）**

添加测试：

```python
@pytest.mark.asyncio
async def test_ocr_file_list_supports_filters_and_pagination() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/04/a.pdf"},
                {"file_name": "b.pdf", "file_size": 11, "object_key": "ocr_file/2026/04/b.pdf"},
                {"file_name": "c.png", "file_size": 12, "object_key": "ocr_file/2026/04/c.png"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text

        listed = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files?page=1&page_size=2&status=INIT&file_name=.pdf",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] >= 2
        assert len(body["items"]) == 2
        assert all(item["status"] == "INIT" for item in body["items"])
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_ocr_file_list_supports_filters_and_pagination -v
```

Expected: FAIL（列表接口未实现或返回结构不匹配）。

- [ ] **Step 3: 实现列表接口**

`router.py` 新增 `GET /workspaces/{workspace_id}/ocr-files`：

```python
@file_router.get("", response_model=OcrFileListPageOut)
async def list_ocr_files(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    file_name: str | None = Query(default=None),
    ocr_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    create_at_start: datetime | None = Query(default=None),
    create_at_end: datetime | None = Query(default=None),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(OcrFile).where(OcrFile.workspace_id == workspace_id)
    if file_name:
        stmt = stmt.where(OcrFile.file_name.ilike(f"%{file_name.strip()}%"))
    if ocr_type:
        stmt = stmt.where(OcrFile.ocr_type == ocr_type.strip())
    if status:
        stmt = stmt.where(OcrFile.status == status.strip())
    if create_at_start is not None:
        stmt = stmt.where(OcrFile.create_at >= create_at_start)
    if create_at_end is not None:
        stmt = stmt.where(OcrFile.create_at <= create_at_end)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await session.execute(
            stmt.order_by(OcrFile.create_at.desc(), OcrFile.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return OcrFileListPageOut(
        items=[OcrFileListItemOut.model_validate(row, from_attributes=True) for row in rows],
        total=int(total or 0),
    )
```

- [ ] **Step 4: 重跑测试确认通过**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_ocr_file_list_supports_filters_and_pagination -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/file_ocr/api/router.py backend/app/file_ocr/api/schemas.py backend/tests/test_file_ocr_api.py
git commit -m "feat(file-ocr): add paginated task list with filters"
```

---

## Task 3: 后端创建任务接口（批量入库）

**Files:**
- Modify: `backend/app/file_ocr/api/router.py`
- Modify: `backend/app/file_ocr/api/schemas.py`
- Modify: `backend/tests/test_file_ocr_api.py`

- [ ] **Step 1: 写失败测试（创建后 status=INIT/page_count 为空）**

新增测试：

```python
@pytest.mark.asyncio
async def test_create_ocr_files_sets_init_status_and_null_page_count() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fc-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 1024, "object_key": "ocr_file/2026/04/a.pdf"}
            ],
        }
        resp = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert resp.status_code == 201, resp.text
        row = resp.json()["items"][0]
        assert row["status"] == "INIT"
        assert row["page_count"] is None
        assert row["file_size"] == 1024
        assert row["object_key"] == "ocr_file/2026/04/a.pdf"
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_create_ocr_files_sets_init_status_and_null_page_count -v
```

Expected: FAIL（创建接口未实现）。

- [ ] **Step 3: 实现创建接口与输入校验**

`schemas.py` 增加：

```python
class OcrFileCreateFileIn(BaseModel):
    file_name: str = Field(min_length=1, max_length=256)
    file_size: int = Field(ge=0, le=50 * 1024 * 1024)
    object_key: str = Field(min_length=1, max_length=1024)


class OcrFileCreateIn(BaseModel):
    ocr_type: Literal["PADDLE_OCR", "MINER_U"]
    files: list[OcrFileCreateFileIn] = Field(min_length=1, max_length=50)
```

`router.py` 增加：

```python
@file_router.post("", response_model=OcrFileBatchCreateOut, status_code=status.HTTP_201_CREATED)
async def create_ocr_files(
    workspace_id: uuid.UUID,
    body: OcrFileCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    rows = []
    for f in body.files:
        row = OcrFile(
            workspace_id=workspace_id,
            file_name=f.file_name.strip(),
            file_size=f.file_size,
            object_key=f.object_key.strip(),
            ocr_type=body.ocr_type,
            status="INIT",
            page_count=None,
        )
        session.add(row)
        rows.append(row)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return OcrFileBatchCreateOut(
        items=[OcrFileListItemOut.model_validate(row, from_attributes=True) for row in rows],
        total=len(rows),
    )
```

- [ ] **Step 4: 重跑测试确认通过**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py::test_create_ocr_files_sets_init_status_and_null_page_count -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/file_ocr/api/router.py backend/app/file_ocr/api/schemas.py backend/tests/test_file_ocr_api.py
git commit -m "feat(file-ocr): add batch create API with INIT defaults"
```

---

## Task 4: 数据库脚本同步（schema_postgresql）

**Files:**
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 写失败校验命令（字段存在性）**

Run:

```bash
rg "file_uri|object_key|file_size|page_count" backend/sql/schema_postgresql.sql
```

Expected: 目前仍出现 `file_uri` 且缺少新增字段定义。

- [ ] **Step 2: 更新 SQL**

调整 `ocr_file` 表定义与注释：

```sql
-- remove file_uri
file_size bigint NULL,
object_key varchar(1024) NOT NULL,
page_count int4 NULL,
```

并补充注释：

```sql
COMMENT ON COLUMN public.ocr_file.file_size IS '文件大小(字节)';
COMMENT ON COLUMN public.ocr_file.object_key IS '文件存储对象键';
COMMENT ON COLUMN public.ocr_file.page_count IS '页数';
```

- [ ] **Step 3: 再次运行校验命令**

Run:

```bash
rg "file_uri|object_key|file_size|page_count" backend/sql/schema_postgresql.sql
```

Expected: 不再有 `file_uri`，新增字段均可检出。

- [ ] **Step 4: 语法快速检查**

Run:

```bash
cd backend && python -m compileall app/file_ocr
```

Expected: PASS（确保同步修改未破坏 Python 模块导入）。

- [ ] **Step 5: Commit**

```bash
git add backend/sql/schema_postgresql.sql
git commit -m "chore(file-ocr): sync ocr_file SQL schema fields"
```

---

## Task 5: 前端 API 层（列表/创建/S3手动上传进度）

**Files:**
- Modify: `minerva-ui/src/api/ocrFile.ts`

- [ ] **Step 1: 写失败类型检查目标**

先在 `ocrFile.ts` 里声明待实现函数签名（仅声明不实现），再运行：

```bash
cd minerva-ui && npm run build
```

Expected: FAIL（调用方或导出缺失，作为红灯起点）。

- [ ] **Step 2: 实现 API 方法**

在 `ocrFile.ts` 增加：

```typescript
export type OcrFileListParams = {
  file_name?: string
  ocr_type?: string
  status?: string
  create_at_start?: string
  create_at_end?: string
  page?: number
  page_size?: number
}

export function listOcrFiles(workspaceId: string, params: OcrFileListParams) {
  const sp = new URLSearchParams()
  if (params.file_name) sp.set('file_name', params.file_name)
  if (params.ocr_type) sp.set('ocr_type', params.ocr_type)
  if (params.status) sp.set('status', params.status)
  if (params.create_at_start) sp.set('create_at_start', params.create_at_start)
  if (params.create_at_end) sp.set('create_at_end', params.create_at_end)
  if (params.page != null) sp.set('page', String(params.page))
  if (params.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<OcrFileListPage>(ocrFilePath(workspaceId, q ? `?${q}` : ''))
}

export function createOcrFiles(workspaceId: string, body: OcrFileCreateBody) {
  return apiJson<OcrFileCreateOut>(ocrFilePath(workspaceId), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function uploadOcrSourceFile(
  workspaceId: string,
  file: File,
  onProgress?: (percent: number) => void,
) { /* XMLHttpRequest + FormData + progress */ }
```

要求：
- `uploadOcrSourceFile` 调用现有 `POST /workspaces/{workspaceId}/s3/files:upload?module_prefix=ocr_file`；
- 返回 `object_key`、`file_name`、`size`；
- 使用 `xhr.upload.onprogress` 回调进度。

- [ ] **Step 3: 运行前端构建确认通过**

Run:

```bash
cd minerva-ui && npm run build
```

Expected: PASS。

- [ ] **Step 4: API 契约检查**

Run:

```bash
rg "listOcrFiles|createOcrFiles|uploadOcrSourceFile" minerva-ui/src/api/ocrFile.ts
```

Expected: 三个导出函数均存在。

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/api/ocrFile.ts
git commit -m "feat(file-ocr-ui): add list create and upload APIs"
```

---

## Task 6: 前端任务列表页（筛选+分页+操作列）

**Files:**
- Modify: `minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx`
- Modify: `minerva-ui/src/features/file-ocr/RulesFileOcrPage.css`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

- [ ] **Step 1: 写失败构建检查**

先在 `RulesFileOcrTasksPage` 引入但未实现新 API，运行：

```bash
cd minerva-ui && npm run build
```

Expected: FAIL（缺失实现/类型不匹配）。

- [ ] **Step 2: 实现列表与筛选 UI**

`RulesFileOcrTasksPage` 目标结构：

```tsx
<Form layout="inline"> {/* file_name, ocr_type, status, create_at range */} </Form>
<Table
  rowKey="id"
  columns={[/* 文件名/OCR类型/状态/文件大小/object_key/页数/创建时间/更新时间/操作 */]}
  pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
/>
```

要求：
- 默认 `pageSize=DEFAULT_PAGE_SIZE`；
- 查询与重置可触发刷新；
- 操作列先给 5 个入口按钮（详情/重跑/下载/删除/取消），未接后端时禁用并提示。

- [ ] **Step 3: 实现样式**

`RulesFileOcrPage.css` 增加筛选栏、表格区域、操作按钮间距、上传进度区基础样式。

- [ ] **Step 4: 运行构建与 lint**

Run:

```bash
cd minerva-ui && npm run build
cd minerva-ui && npm run lint
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx minerva-ui/src/features/file-ocr/RulesFileOcrPage.css minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "feat(file-ocr-ui): implement task list filters and table"
```

---

## Task 7: 两屏新增弹窗（不可关闭 + 手动上传 + 进度 + 完成入库）

**Files:**
- Modify: `minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx`
- Modify: `minerva-ui/src/features/file-ocr/RulesFileOcrPage.css`

- [ ] **Step 1: 写失败流程检查（构建+关键文案）**

Run:

```bash
cd minerva-ui && npm run build
rg "上一步|下一步|完成|PaddleOCR|MinerU" minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx
```

Expected: 第二条命令在实现前缺少完整流程关键字。

- [ ] **Step 2: 实现两屏不可关闭弹窗**

弹窗关键参数与步骤：

```tsx
<Modal
  open={wizardOpen}
  maskClosable={false}
  keyboard={false}
  closable={false}
  footer={null}
>
  {step === 1 ? <StepOneSelectOcrType /> : <StepTwoUploadFiles />}
</Modal>
```

步骤按钮：

```tsx
{step === 1 ? (
  <Button type="primary" onClick={nextStep} disabled={!ocrType}>下一步</Button>
) : (
  <>
    <Button onClick={prevStep} disabled={submitting}>上一步</Button>
    <Button type="primary" loading={submitting} onClick={finishCreate}>完成</Button>
  </>
)}
```

- [ ] **Step 3: 实现手动上传与入库**

`finishCreate` 逻辑：

```tsx
for (const file of selectedFiles) {
  const uploaded = await uploadOcrSourceFile(workspaceId, file.originFileObj!, (p) => updateProgress(file.uid, p))
  createPayload.files.push({
    file_name: file.name,
    file_size: file.size ?? uploaded.size,
    object_key: uploaded.object_key,
  })
}
await createOcrFiles(workspaceId, { ocr_type: ocrType, files: createPayload.files })
```

校验：
- 扩展名：`pdf/jpg/jpeg/png`
- 单文件：`<=50MB`
- 数量：`<=50`
- 上传组件 `beforeUpload={() => false}` 禁止自动上传

- [ ] **Step 4: 构建验证**

Run:

```bash
cd minerva-ui && npm run build
cd minerva-ui && npm run lint
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx minerva-ui/src/features/file-ocr/RulesFileOcrPage.css
git commit -m "feat(file-ocr-ui): add two-step non-closable create wizard with upload progress"
```

---

## Task 8: 联调验证与最终回归

**Files:**
- Modify: `backend/tests/test_file_ocr_api.py`
- Modify: `backend/app/file_ocr/api/router.py`（仅在联调发现缺口时）
- Modify: `minerva-ui/src/features/file-ocr/RulesFileOcrPage.tsx`（仅在联调发现缺口时）

- [ ] **Step 1: 后端测试全量 file_ocr**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py -v
```

Expected: PASS。

- [ ] **Step 2: 前端静态质量检查**

Run:

```bash
cd minerva-ui && npm run build
cd minerva-ui && npm run lint
```

Expected: PASS。

- [ ] **Step 3: 手工联调清单**

手工验证以下路径：
- 任务列表过滤四个条件可用；
- 分页默认 10 且可切换；
- 两屏流程必须走“下一步 -> 完成”；
- 对话框不可关闭（遮罩/ESC/右上角）；
- 进度条可见；
- 创建成功后列表可见 `object_key`、`file_size`、`status=INIT`。

- [ ] **Step 4: 修补联调问题并重跑**

Run:

```bash
cd backend && pytest tests/test_file_ocr_api.py -v
cd minerva-ui && npm run build
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/file_ocr backend/sql/schema_postgresql.sql backend/tests/test_file_ocr_api.py minerva-ui/src/api/ocrFile.ts minerva-ui/src/features/file-ocr minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "feat(file-ocr): implement task list filters and two-step create flow"
```

---

## Spec 对照自检（计划作者填写）

| 规格要求 | 对应任务 |
|---|---|
| 列表字段（含 file_size/object_key/page_count） | Task 1, Task 2, Task 6 |
| 过滤条件（file_name/ocr_type/status/创建时间范围） | Task 2, Task 6 |
| 默认分页10 + 页大小下拉 | Task 2, Task 6 |
| 新增流程两屏（类型选择 + 上传完成） | Task 7 |
| 上传限制（后缀/大小/数量） | Task 7 |
| 手动上传 + 上传进度 | Task 5, Task 7 |
| 对话框不可关闭 | Task 7 |
| status 初始 INIT，page_count 默认空 | Task 3 |
| 删除 file_uri，路径展示 object_key | Task 1, Task 4, Task 6 |

**Placeholder 扫描:** 本计划无 TBD/TODO/“后续补充”类占位。  
**类型一致性:** 全链路统一使用 `object_key`、`file_size`、`page_count` 与 `status=INIT` 命名。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-04-30-file-ocr-task-list-and-create.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
