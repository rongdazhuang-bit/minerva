# 排版保真 OCR / 翻译（Layout Block 中间层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在文件 OCR 与文档翻译全链路中，以 LDM（Layout Block）为真源，同时实现结构排版与视觉排版保真，公式块不翻译，页级/段落对照用 `MinervaMarkdown`（`preset="ocr"`）渲染。

**Architecture:** 新建 `backend/app/layout/` 提供 `LayoutBlock`、`from_paddle`、`to_markdown`、`overflow` 与按格式 `writers`；OCR Paddle 策略持久化 `layout_blocks_json` 与页图；翻译 `extract` 写 `layout_snapshot_json`，`assemble` 走 `LayoutWriter`；前端新增 `layout-pages` API 消费与 `LayoutPageViewer` + 详情 Tab。历史任务无 LDM 时 API 回退既有 `markdown_text`。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PyMuPDF, python-docx, openpyxl, Celery, React 18, Ant Design, TanStack Query, `MinervaMarkdown`（react-markdown + KaTeX）。

**设计依据:** `docs/superpowers/specs/2026-05-22-layout-preserving-ocr-translate-design.md`

---

## 文件结构（将创建 / 将修改）

### 后端（新建）

| 路径 | 职责 |
|------|------|
| `backend/app/layout/__init__.py` | 包导出 |
| `backend/app/layout/models.py` | `LayoutBlock`, `LayoutDocument`, `LayoutPage` Pydantic |
| `backend/app/layout/labels.py` | Paddle label → 归一化 label / overflow / skip_translate |
| `backend/app/layout/from_paddle.py` | `prunedResult` → `LayoutDocument` |
| `backend/app/layout/to_markdown.py` | 页/文档 → `source_markdown` / `translated_markdown` |
| `backend/app/layout/overflow.py` | `fit_text_to_box`, `OverflowResult` |
| `backend/app/layout/page_raster.py` | PDF/图像页 → PNG 上传 S3 |
| `backend/app/layout/segments.py` | `LayoutDocument` → `list[SegmentDraft]` |
| `backend/app/layout/from_docx.py` | docx → LDM |
| `backend/app/layout/from_pdf_text.py` | PyMuPDF 文字层 → LDM |
| `backend/app/layout/from_plain.py` | txt/md/csv/xlsx 结构块 |
| `backend/app/layout/writers/base.py` | `LayoutWriter` 协议 |
| `backend/app/layout/writers/pdf_writer.py` | 底图 + bbox 叠字 / redact+textbox |
| `backend/app/layout/writers/docx_writer.py` | 段落/单元格 + expand 行高 |
| `backend/app/layout/writers/xlsx_writer.py` | openpyxl 写回 |
| `backend/app/layout/writers/text_writer.py` | txt/md/csv |
| `backend/app/file_ocr/service/layout_pages.py` | 组装 OCR `layout-pages` 响应 |
| `backend/app/translate/service/layout_pages.py` | 组装翻译 `layout-pages` 响应 |
| `backend/tests/test_layout_labels.py` | label / 公式 skip |
| `backend/tests/test_layout_from_paddle.py` | 样例 prunedResult |
| `backend/tests/test_layout_to_markdown.py` | 公式原文不变 |
| `backend/tests/test_layout_overflow.py` | shrink / expand |
| `backend/tests/test_ocr_layout_pages_api.py` | layout-pages 路由 |
| `backend/tests/test_translate_layout_pipeline.py` | 公式段跳过 LLM |

### 后端（修改）

| 路径 | 变更 |
|------|------|
| `backend/sql/schema_postgresql.sql` | `ocr_file_paddleocr` / `ocr_file_mineru` / `doc_translate_job` 新列 |
| `backend/app/file_ocr/domain/db/models_result.py` | ORM 新列 |
| `backend/app/translate/domain/db/models.py` | `layout_snapshot_json`, `layout_source` |
| `backend/app/file_ocr/service/strategies/paddle.py` | 持久化 LDM + 页图 + 派生 markdown |
| `backend/app/file_ocr/service/markdown_pages.py` | 有 LDM 时派生 markdown |
| `backend/app/file_ocr/api/schemas.py` | `LayoutPagesOut` 等 |
| `backend/app/file_ocr/api/router.py` | `GET .../layout-pages` |
| `backend/app/translate/service/ocr_bridge.py` | 返回 `LayoutDocument` 而非仅 markdown 元组 |
| `backend/app/translate/service/run_pipeline.py` | snapshot、skip formula、assemble→writer |
| `backend/app/translate/service/strategies/*.py` | 委托 `app/layout` 抽取/写回 |
| `backend/app/translate/api/schemas.py` | `group_by` segments、`layout-pages` |
| `backend/app/translate/api/router.py` | 新端点 |
| `backend/app/translate/infrastructure/repository.py` | 更新 job layout 字段 |
| `backend/app/config.py` | `layout_page_raster_prefix`, `layout_version` |
| `backend/.env.example`, `backend/.env.dev` | 同步 |

### 前端（新建）

| 路径 | 职责 |
|------|------|
| `frontend/src/api/layoutPages.ts` | `getOcrLayoutPages`, `getTranslateLayoutPages` 类型 |
| `frontend/src/components/layout/LayoutPageViewer.tsx` | 底图 + bbox overlay + 双栏 Markdown |
| `frontend/src/components/layout/LayoutPageViewer.css` | 定位样式 |

### 前端（修改）

| 路径 | 变更 |
|------|------|
| `frontend/src/api/ocrTask.ts` | layout-pages 类型与请求 |
| `frontend/src/api/translate.ts` | layout-pages、`group_by` segments |
| `frontend/src/features/file-ocr/FileOcrTaskPage.tsx` | Drawer Tabs：版面 / Markdown |
| `frontend/src/features/translate/TranslatePage.tsx` | 详情 Tabs；`MinervaMarkdown` 对照 |
| `frontend/src/i18n/locales/zh-CN.json`, `en.json` | Tab 文案 |

---

## Task 1: Layout 核心模型与 label 映射

**Files:**
- Create: `backend/app/layout/models.py`
- Create: `backend/app/layout/labels.py`
- Create: `backend/tests/test_layout_labels.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_layout_labels.py
from app.layout.labels import normalize_block_label


def test_formula_labels_skip_translate() -> None:
    meta = normalize_block_label("inline_formula")
    assert meta.label == "formula"
    assert meta.skip_translate is True
    assert meta.overflow_policy == "skip"


def test_text_label_shrink() -> None:
    meta = normalize_block_label("text")
    assert meta.label == "text"
    assert meta.skip_translate is False
    assert meta.overflow_policy == "shrink"


def test_title_label_expand() -> None:
    meta = normalize_block_label("doc_title")
    assert meta.label == "title"
    assert meta.overflow_policy == "expand"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_layout_labels.py -v
```

Expected: `ModuleNotFoundError: app.layout`

- [ ] **Step 3: 实现 models + labels**

`models.py` 使用 Pydantic v2：

```python
class LayoutBlock(BaseModel):
    block_key: str
    parent_key: str | None = None
    label: str
    reading_order: int
    source_text: str
    translated_text: str | None = None
    bbox: list[float] | None = None  # [x0,y0,x1,y1]
    page_index: int | None = None
    sheet_name: str | None = None
    table_grid: dict[str, int] | None = None
    style_hint: dict[str, object] | None = None
    overflow_policy: Literal["shrink", "expand", "skip"] = "shrink"
    skip_translate: bool = False

class LayoutPage(BaseModel):
    page_index: int
    width: int | None = None
    height: int | None = None
    blocks: list[LayoutBlock] = Field(default_factory=list)

class LayoutDocument(BaseModel):
    pages: list[LayoutPage] = Field(default_factory=list)
    layout_source: Literal["native", "ocr", "hybrid"] = "native"
```

`labels.py`：`FORMULA_LABELS = frozenset({...})`；`normalize_block_label(raw: str) -> BlockLabelMeta`。

- [ ] **Step 4: 运行测试通过**

```bash
cd backend && pytest tests/test_layout_labels.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/layout backend/tests/test_layout_labels.py
git commit -m "feat(layout): add LayoutBlock models and label normalization"
```

---

## Task 2: from_paddle + to_markdown

**Files:**
- Create: `backend/app/layout/from_paddle.py`
- Create: `backend/app/layout/to_markdown.py`
- Create: `backend/tests/test_layout_from_paddle.py`
- Create: `backend/tests/test_layout_to_markdown.py`

- [ ] **Step 1: 写 from_paddle 失败测试**

使用 `backend/tests/test_paddleocr_vl_client.py` 中 `test_pruned_result_parses_service_like_payload` 的 raw dict，断言：

- `p0.b0` 的 `source_text == "ICS 35.240.15"`
- `header_image` → `skip_translate=True`, `label=="figure"`

另增公式块 raw：

```python
{
    "block_label": "formula",
    "block_content": "$E=mc^2$",
    "block_bbox": [10, 10, 100, 30],
    "block_id": 5,
    "block_order": 3,
    "group_id": 5,
}
```

断言 `label=="formula"` 且 `skip_translate`。

- [ ] **Step 2: 实现 from_paddle**

```python
def layout_document_from_pruned(page_index: int, pr: PrunedResult) -> LayoutPage:
    blocks: list[LayoutBlock] = []
    for item in sorted(pr.parsing_res_list, key=lambda b: (b.block_order is None, b.block_order or 0, b.block_id)):
        meta = normalize_block_label(item.block_label)
        if not (item.block_content or "").strip() and meta.label == "figure":
            content = ""
        else:
            content = item.block_content
        blocks.append(LayoutBlock(
            block_key=f"p{page_index}.b{item.block_id}",
            label=meta.label,
            reading_order=item.block_order or item.block_id,
            source_text=content,
            bbox=list(item.block_bbox) if len(item.block_bbox) >= 4 else None,
            page_index=page_index,
            overflow_policy=meta.overflow_policy,
            skip_translate=meta.skip_translate,
        ))
    return LayoutPage(page_index=page_index, width=pr.width, height=pr.height, blocks=blocks)
```

- [ ] **Step 3: 写 to_markdown 失败测试**

公式块 `source_text="$E=mc^2$"` 编入文档后 `page_markdown_source(page)` 仍含 `$E=mc^2$`；`page_markdown_translated` 对 `skip_translate` 块使用相同字符串。

- [ ] **Step 4: 实现 to_markdown**

- 按 `reading_order` 拼接块；`label==title` 前缀 `## `（或保留块内已有 markdown 标题符）
- `figure` 且内容为 HTML div：输出 `markdown_images` 占位，不重复 HTML
- `table`：原样输出 `block_content`（多为 HTML table）
- 提供 `def page_markdown(page: LayoutPage, *, use_translation: bool) -> str`

- [ ] **Step 5: pytest 通过后 commit**

```bash
git commit -m "feat(layout): paddle import and markdown export"
```

---

## Task 3: overflow 与 segments 辅助

**Files:**
- Create: `backend/app/layout/overflow.py`
- Create: `backend/app/layout/segments.py`
- Create: `backend/tests/test_layout_overflow.py`

- [ ] **Step 1: overflow 测试**

```python
from app.layout.overflow import fit_text_to_box

def test_shrink_reduces_font_until_fits() -> None:
    r = fit_text_to_box("hello world", width=50, height=20, policy="shrink", base_font_pt=12.0)
    assert r.font_size_pt <= 12.0
    assert r.truncated is False

def test_shrink_truncates_when_min_font_exceeded() -> None:
    long_text = "x" * 500
    r = fit_text_to_box(long_text, width=30, height=10, policy="shrink", base_font_pt=6.0, min_font_pt=6.0)
    assert r.truncated is True
```

- [ ] **Step 2: 实现 fit_text_to_box**

返回 `OverflowResult(text, font_size_pt, truncated, warning)`；`expand` 策略首期仅返回 `font_size_pt=base` 与 `expanded_height` 估算（供 writer 使用）。

- [ ] **Step 3: segments.py**

```python
def layout_to_segment_drafts(doc: LayoutDocument, *, max_chars: int = 6000) -> list[SegmentDraft]:
    """One draft per translatable block; split long text with sub_index in anchor_json."""
```

`skip_translate` 块仍生成 draft（供对照展示），`anchor_json` 含 `"skip_translate": true`；流水线翻译阶段跳过 LLM。

- [ ] **Step 4: pytest + commit**

---

## Task 4: 数据库列与 ORM

**Files:**
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/file_ocr/domain/db/models_result.py`
- Modify: `backend/app/translate/domain/db/models.py`
- Create: `backend/tests/test_layout_db_columns.py`

- [ ] **Step 1: SQL ALTER（无 FK）**

`ocr_file_paddleocr` / `ocr_file_mineru` 增加：

```sql
ALTER TABLE public.ocr_file_paddleocr ADD COLUMN IF NOT EXISTS page_width integer;
ALTER TABLE public.ocr_file_paddleocr ADD COLUMN IF NOT EXISTS page_height integer;
ALTER TABLE public.ocr_file_paddleocr ADD COLUMN IF NOT EXISTS layout_blocks_json jsonb;
ALTER TABLE public.ocr_file_paddleocr ADD COLUMN IF NOT EXISTS page_raster_object_key character varying(1024);
ALTER TABLE public.ocr_file_paddleocr ADD COLUMN IF NOT EXISTS layout_version smallint DEFAULT 1;
```

`doc_translate_job` 增加：

```sql
ALTER TABLE public.doc_translate_job ADD COLUMN IF NOT EXISTS layout_snapshot_json jsonb;
ALTER TABLE public.doc_translate_job ADD COLUMN IF NOT EXISTS layout_source character varying(32);
```

- [ ] **Step 2: ORM Mapped 列与注释（code-comments 规范）**

- [ ] **Step 3: 测试 ORM 表名与列名存在**

```python
def test_paddleocr_has_layout_blocks_json() -> None:
    assert "layout_blocks_json" in OcrFilePaddleocr.__table__.columns
```

- [ ] **Step 4: commit**

---

## Task 5: Paddle OCR 持久化 LDM + 页图

**Files:**
- Create: `backend/app/layout/page_raster.py`
- Modify: `backend/app/file_ocr/service/strategies/paddle.py`
- Modify: `backend/app/config.py`, `backend/.env.example`, `backend/.env.dev`

- [ ] **Step 1: page_raster**

- PDF：`fitz` 按页 `get_pixmap` → PNG bytes → `S3FileService.upload` 到 `{layout_page_raster_prefix}/{workspace_id}/{ocr_file_id}/p{n}.png`
- 图像：单页原图作为 raster
- 函数：`async def upload_page_rasters(...) -> dict[int, str]` 返回 `page_index → object_key`

- [ ] **Step 2: 修改 paddle.py process 循环**

对每个 `layout_parsing_results` 页：

1. `pr = page.pruned_result`；`layout_page = layout_document_from_pruned(idx, pr)`
2. `layout_blocks_json = layout_page.model_dump(mode="json")["blocks"]` 存行（或整页 blocks 列表）
3. `page_width/height` 写入
4. `markdown_text, images = page_markdown_with_images(layout_page)` 派生写库
5. 任务结束后批量上传页图并回写 `page_raster_object_key`

- [ ] **Step 3: 本地/单测 mock**

扩展 `backend/tests/test_file_ocr_paddle_config.py` 或新建集成测试：mock `post_layout_parsing` 返回带 `parsing_res_list` 的 envelope，断言 session 新增行含非空 `layout_blocks_json`。

- [ ] **Step 4: commit**

---

## Task 6: OCR layout-pages API

**Files:**
- Create: `backend/app/file_ocr/service/layout_pages.py`
- Modify: `backend/app/file_ocr/api/schemas.py`
- Modify: `backend/app/file_ocr/api/router.py`
- Create: `backend/tests/test_ocr_layout_pages_api.py`

- [ ] **Step 1: schemas**

```python
class LayoutBlockOut(BaseModel):
    block_key: str
    label: str
    source_text: str
    bbox: list[float] | None
    overflow_policy: str
    skip_translate: bool

class OcrLayoutPageOut(BaseModel):
    page_index: int
    width: int | None
    height: int | None
    blocks: list[LayoutBlockOut]
    page_raster_url: str | None
    source_markdown: str
    images: dict[str, str] | None
```

- [ ] **Step 2: layout_pages service**

- 校验 `ocr_file.status == SUCCESS`
- 读 `ocr_file_paddleocr` 行；无 `layout_blocks_json` → `AppError("layout.blocks_missing", ..., 404)`
- `page_raster_url`：复用现有 S3 download proxy 生成短期 URL（与 file download 一致模式）
- `source_markdown`：`to_markdown` 派生

- [ ] **Step 3: router**

`GET /workspaces/{workspace_id}/ocr-files/{ocr_file_id}/layout-pages`

- [ ] **Step 4: API 测试**（TestClient + 种子行）

- [ ] **Step 5: commit**

---

## Task 7: markdown-pages 回退与兼容

**Files:**
- Modify: `backend/app/file_ocr/service/markdown_pages.py`

- [ ] **Step 1: 当 `layout_blocks_json` 非空**

由 LDM 现场生成 `markdown_text` / `images`（与库内字段一致则可直接返回库内缓存）

- [ ] **Step 2: 当为空（历史任务）**

保持现有读 `markdown_text` 逻辑

- [ ] **Step 3: 回归现有 markdown-pages 测试（若有）**

- [ ] **Step 4: commit**

---

## Task 8: 翻译抽取接 LDM + 公式跳过 LLM

**Files:**
- Create: `backend/app/layout/from_docx.py`, `from_pdf_text.py`, `from_plain.py`
- Modify: `backend/app/translate/service/strategies/*.py`
- Modify: `backend/app/translate/service/ocr_bridge.py`
- Modify: `backend/app/translate/service/run_pipeline.py`
- Modify: `backend/app/translate/infrastructure/repository.py`
- Create: `backend/tests/test_translate_layout_pipeline.py`

- [ ] **Step 1: ocr_bridge 扩展**

```python
async def run_ocr_and_load_layout(
    session, *, workspace_id, job_id, ...
) -> tuple[uuid.UUID, LayoutDocument]:
```

从 DB 读 `layout_blocks_json` 组装 `LayoutDocument`，`layout_source="ocr"`。

- [ ] **Step 2: pdf_strategy.extract**

- 有 `LayoutDocument`：`layout_to_segment_drafts(doc)`，anchor 含 `block_key`
- 无 OCR：`from_pdf_text` 生成 LDM

- [ ] **Step 3: docx/xlsx/txt/md/csv 策略**

抽取改为 `from_docx` / `from_plain`，返回 drafts + `LayoutDocument`；`run_pipeline` 在 `EXTRACTING` 后：

```python
await translate_repo.update_doc_translate_job(
    session, job_id=job_id, workspace_id=workspace_id,
    layout_snapshot_json=doc.model_dump(mode="json"),
    layout_source=doc.layout_source,
)
```

- [ ] **Step 4: run_pipeline 翻译循环**

```python
anchor = seg.anchor_json or {}
if anchor.get("skip_translate"):
    translated = seg.source_text
else:
    translated = await translate_segment(...)
```

- [ ] **Step 5: 测试**

mock LLM，注入含 formula 块的 snapshot，断言 formula 段 `translate_segment` 未被调用（patch mock）。

- [ ] **Step 6: commit**

---

## Task 9: LayoutWriter 写回（下载 A）

**Files:**
- Create: `backend/app/layout/writers/*.py`
- Modify: `backend/app/translate/service/strategies/pdf_strategy.py` 等 `assemble` 委托 writer
- Modify: `backend/app/translate/service/run_pipeline.py` ASSEMBLING 步骤

- [ ] **Step 1: pdf_writer**

- `layout_source==ocr`：每页插入底图（`page_raster_object_key` 下载）→ 按 bbox `insert_textbox` + `fit_text_to_box`
- 文字层：保留现有 redact 逻辑，改用 `overflow`
- 公式块：不绘制覆盖（底图保留）

- [ ] **Step 2: docx_writer / xlsx_writer / text_writer**

- docx：按 `block_key` 或 legacy anchor 写段落/单元格；`expand` 时增大行高
- xlsx：单元格写回 + 行高
- txt/md/csv：按序拼接（与现策略等价）

- [ ] **Step 3: registry**

```python
def get_layout_writer(ext: str) -> LayoutWriter: ...
```

- [ ] **Step 4: 策略单测 roundtrip**

小 docx/txt 样例 + 含公式 md 样例；公式译文等于原文。

- [ ] **Step 5: commit**

---

## Task 10: 翻译 layout-pages + segments group_by

**Files:**
- Create: `backend/app/translate/service/layout_pages.py`
- Modify: `backend/app/translate/api/schemas.py`, `router.py`
- Create: `backend/tests/test_translate_layout_api.py`

- [ ] **Step 1: GET `/translate/jobs/{id}/layout-pages`**

从 `layout_snapshot_json` 构建 pages；合并 DB 中 segment 的 `translated_text` 到块；输出 `source_markdown` + `translated_markdown` + `images`（来自 OCR 关联页，若 pdf 扫描）

- [ ] **Step 2: segments `group_by` 查询参数**

```python
group_by: Literal["page", "label", "none"] = "page"
```

响应：

```python
class SegmentGroupOut(BaseModel):
    page_index: int | None
    label: str | None
    segments: list[DocTranslateSegmentOut]

class DocTranslateSegmentListOut(BaseModel):
    segments: list[DocTranslateSegmentOut]  # group_by=none
    groups: list[SegmentGroupOut] | None = None
```

分组键：`anchor_json.page_index`，其次 `anchor_json.label`。

- [ ] **Step 3: API 测试**

- [ ] **Step 4: commit**

---

## Task 11: 前端 API + LayoutPageViewer

**Files:**
- Create: `frontend/src/api/layoutPages.ts`
- Create: `frontend/src/components/layout/LayoutPageViewer.tsx`
- Create: `frontend/src/components/layout/LayoutPageViewer.css`
- Modify: `frontend/src/api/ocrTask.ts`, `translate.ts`

- [ ] **Step 1: TypeScript 类型与请求函数**

```typescript
export type LayoutPageOut = {
  page_index: number
  width: number | null
  height: number | null
  blocks: LayoutBlockOut[]
  page_raster_url: string | null
  source_markdown: string
  translated_markdown?: string | null
  images?: Record<string, string> | null
}
```

- [ ] **Step 2: LayoutPageViewer**

- 顶：页码 Tabs 或滚动锚点
- 中：`page_raster_url` 存在时 `<img>` + 绝对定位半透明 bbox（`left/top/width/height` 为百分比）
- 下：双栏（翻译）或单栏（OCR）`MinervaMarkdown preset="ocr"`

- [ ] **Step 3: 样式**

复用 `minerva-scrollbar-styled`；bbox overlay `pointer-events: none`

- [ ] **Step 4: commit**

---

## Task 12: OCR 详情 Drawer Tabs

**Files:**
- Modify: `frontend/src/features/file-ocr/FileOcrTaskPage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: 状态**

`detailTab: 'layout' | 'markdown'`；打开 SUCCESS 任务时 `useQuery` 拉 `layout-pages`（layout Tab）与现有 `markdown-pages`（markdown Tab）

- [ ] **Step 2: Tabs UI**

```tsx
<Tabs activeKey={detailTab} onChange={setDetailTab} items={[
  { key: 'layout', label: t('fileOcr.tasks.detail.tabLayout'), children: <LayoutPageViewer pages={layoutData.pages} mode="source" /> },
  { key: 'markdown', label: t('fileOcr.tasks.detail.tabMarkdown'), children: /* 现有 MinervaMarkdown 列表 */ },
]} />
```

- [ ] **Step 3: layout-pages 失败回退**

提示并建议切 Markdown Tab（历史任务）

- [ ] **Step 4: commit**

---

## Task 13: 翻译详情 — 页面对照 + Markdown 段落对照

**Files:**
- Modify: `frontend/src/features/translate/TranslatePage.tsx`
- Modify: `frontend/src/features/translate/TranslatePage.css`
- Modify: `frontend/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: 详情 Modal Tabs**

- `pages`：`layout-pages` 双栏 `MinervaMarkdown`
- `segments`：现有对照区改为 `groups.map` 折叠 Panel（Ant `Collapse`），每项内左右 `MinervaMarkdown`

```tsx
<MinervaMarkdown preset="ocr" markdown={s.source_text} images={pageImages} />
<MinervaMarkdown preset="ocr" markdown={s.translated_text ?? ''} images={pageImages} />
```

- [ ] **Step 2: segments 请求**

`getTranslateJobSegments(id, { group_by: 'page' })` 默认

- [ ] **Step 3: 轮询**

非终态时同时刷新 `layout-pages` 与 `segments`（3s，与现 progress 一致）

- [ ] **Step 4: commit**

---

## Task 14: 文档回填与终验

**Files:**
- Modify: `docs/superpowers/specs/2026-05-22-layout-preserving-ocr-translate-design.md` — 状态改为「已实现」并注明实现日期
- Modify: `docs/superpowers/specs/2026-05-20-document-translate-design.md` — 增加交叉引用

- [ ] **Step 1: 后端全量测试**

```bash
cd backend && pytest tests/test_layout_*.py tests/test_ocr_layout_pages_api.py tests/test_translate_layout*.py -v
```

- [ ] **Step 2: 前端 lint/build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: 手工冒烟**

1. 新建 Paddle OCR PDF 任务 → 详情「版面预览」见 bbox + Markdown
2. 新建翻译（含公式 md 或扫描 pdf）→ 页面对照公式左右一致 → 下载文件打开检查

- [ ] **Step 4: 更新 spec 状态 + commit**

---

## Spec 覆盖自检

| Spec 章节 | 任务 |
|-----------|------|
| LDM / labels / 公式 | Task 1–2, 8 |
| 溢出策略 | Task 3, 9 |
| DB 新列 | Task 4 |
| OCR 持久化 + 页图 | Task 5 |
| OCR layout-pages + markdown 兼容 | Task 6–7 |
| 翻译 extract/assemble/Celery | Task 8–9 |
| 下载 A | Task 9 |
| 预览 B | Task 11–12 |
| 对照 C + MinervaMarkdown | Task 10, 13 |
| 错误码 layout.* | Task 6, 10 |
| config/env | Task 5 |
| MinerU 预留 | Task 4 ORM mineru 同列 |

## 执行顺序依赖

```text
Task 1 → 2 → 3 → 4 → 5 → 6 → 7
                ↘
Task 4 ─────────→ 8 → 9 → 10
Task 11 可与 6 并行；Task 12 依赖 6；Task 13 依赖 10
Task 14 最后
```
