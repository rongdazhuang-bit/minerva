# 文档 OCR / 翻译：结构 + 视觉排版保真（Layout Block 中间层）设计说明

**日期**：2026-05-22  
**状态**：已实现（2026-05-22 内联执行首期）  
**范围**：文件 OCR（Paddle 优先）与文档翻译全格式；统一 Layout Document Model（LDM）；可下载保版文件（A）、应用内版面/Markdown 预览（B）、段落对照保结构且 **Markdown 渲染**（C）；允许新增表字段；数据库无外键。

**依据**：

- 现有文档翻译：`docs/superpowers/specs/2026-05-20-document-translate-design.md`
- Paddle layout-parsing / `prunedResult`：`backend/app/ocr/paddleocr/pruned_result.py`
- 前端 Markdown 组件：`minerva-ui/src/components/markdown/MinervaMarkdown.tsx`（`preset="ocr"`）

---

## 1. 目标与成功标准

### 1.1 目标

- **统一真源**：引入 **Layout Block 中间层（LDM）**，OCR 抽取与翻译写回、预览、下载共用同一套块列表。
- **结构排版**：标题层级、段落顺序、表格行列、列表、分栏逻辑与原文一致。
- **视觉排版**：PDF/扫描件在页图底图上按 `bbox` 叠字；Office 尽力保留段落/单元格样式；溢出按块类型混合策略处理。
- **公式**：公式块 **不机器翻译**，保留原文 LaTeX/Markdown 数学片段。
- **对照展示**：页面级与段落级原文/译文对照均通过 **`MinervaMarkdown`（`preset="ocr"`）** 渲染，复用现有 KaTeX/GFM/图片占位能力。

### 1.2 成功标准

| 能力 | 标准 |
|------|------|
| OCR 任务 | SUCCESS 后 `layout-pages` 含块坐标；`markdown-pages` 与块可逆；详情可版面预览 + Markdown Tab |
| 翻译任务 | 下载物扩展名不变，版式肉眼可接受；详情 Modal 页级 Markdown 双栏对照 + 分组段落对照 |
| 公式 | 译文中公式与原文一致（LaTeX 不变） |
| 数据 | 新任务写入 `layout_blocks_json`；历史任务 markdown API 仍可用 |

### 1.3 非目标（本期）

- MinerU 完整 LDM 适配（表字段预留，实现随 MinerU 上线）。
- PDF 多栏全局块推挤/复杂避让。
- 浏览器内可编辑 PDF、术语表、失败段单独重试。
- 将 `MinervaMarkdown` 替换为自定义公式渲染栈。

---

## 2. 架构：方案 1 — Layout Block 中间层

### 2.1 LayoutBlock 模型

```text
LayoutBlock {
  block_key: str              # 全局唯一，如 "p0.b12"、"sheet1.r3.c2"
  parent_key: str | null     # 表格/分组
  label: str                 # title | text | table | table_cell | formula | figure | footnote | ...
  reading_order: int
  source_text: str
  translated_text: str | null
  bbox: [x0,y0,x1,y1] | null # 页坐标（PDF/OCR）
  page_index: int | null
  sheet_name: str | null
  table_grid: { row, col, rowspan?, colspan? } | null
  style_hint: { font_size_pt?, bold?, align? } | null
  overflow_policy: "shrink" | "expand" | "skip"
  skip_translate: bool
}
```

**Paddle `block_label` 归一化**（`app/layout/labels.py`）：

| 检测 label（示例） | 内部 label | overflow | 翻译 |
|--------------------|------------|----------|------|
| text, paragraph, number | text | shrink | 是 |
| footnote, footer, caption | footnote | shrink | 是 |
| title, doc_title, paragraph_title | title | expand | 是 |
| table | table | expand | 是（尽量拆 table_cell） |
| **formula, equation, inline_formula, interline_equation** 等 | **formula** | skip | **否** |
| figure, image, chart, seal, header_image | figure | skip | 否 |

**公式块规则**：

- `skip_translate=true`；`translated_text` 组装时 **强制等于 `source_text`**（保留 `$...$`、`$$...$$`、`\(...\)` 等）。
- `to_markdown` 输出时公式块原样嵌入，供 `MinervaMarkdown` + `normalizeMarkdownForOcr` 渲染。
- 段落翻译流水线 **不调用 LLM** 处理公式块；若误合并进大段，抽取阶段应拆出独立 `block_key`。

### 2.2 溢出策略（混合 C）

| 策略 | 适用 label | 行为 |
|------|------------|------|
| shrink | text, footnote | bbox 内缩小字号；仍溢出则截断 + warning |
| expand | title, table_cell | 扩高/撑行高；标题有限扩宽 |
| skip | formula, figure | 不译、不写回替换（图保留底图） |

实现：`app/layout/overflow.py` 的 `fit_text_to_box()`，PDF/预览/Office 写回共用。

### 2.3 模块划分

```text
backend/app/layout/
  models.py              # LayoutBlock, LayoutDocument
  labels.py              # label 归一化 + overflow + skip_translate
  from_paddle.py
  from_docx.py / from_pdf_text.py / from_xlsx.py / from_plain.py
  to_markdown.py         # LDM → 页级/块级 Markdown（公式原样）
  overflow.py
  writers/               # pdf, docx, xlsx, text

backend/app/file_ocr/     # 调用 from_paddle，持久化 LDM
backend/app/translate/    # extract → layout_snapshot；assemble → writers
```

---

## 3. 数据模型（新增字段，无外键）

### 3.1 `ocr_file_paddleocr` / `ocr_file_mineru`（每页）

| 列名 | 类型 | 说明 |
|------|------|------|
| `page_width` | int, nullable | 页宽 |
| `page_height` | int, nullable | 页高 |
| `layout_blocks_json` | jsonb, nullable | `LayoutBlock[]` 真源 |
| `page_raster_object_key` | varchar(1024), nullable | 页图（PDF/图像 OCR） |
| `layout_version` | smallint | 默认 `1` |

保留 `markdown_text`、`markdown_images`：由 LDM **派生**（新任务双写；旧任务仅 markdown 仍可读）。

### 3.2 `doc_translate_job`

| 列名 | 类型 | 说明 |
|------|------|------|
| `layout_snapshot_json` | jsonb, nullable | 抽取完成后的 LDM |
| `layout_source` | varchar(32) | `native` / `ocr` / `hybrid` |

### 3.3 `doc_translate_segment`

不新增列；`anchor_json` 扩展：

```json
{
  "block_key": "p0.b12",
  "sub_index": 0,
  "label": "formula",
  "overflow_policy": "skip",
  "skip_translate": true
}
```

与既有 docx/pdf 锚点字段并存。

### 3.4 SQL

- 更新 `backend/sql/schema_postgresql.sql`（ALTER ADD COLUMN，无 FK）。
- ORM 同步；`create_missing_tables` 引导新列。

---

## 4. HTTP API

### 4.1 文件 OCR

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `.../ocr-files/{id}/layout-pages` | 页列表 + `blocks` + `page_raster_url?` + **页级 `source_markdown` / `translated_markdown`（翻译任务 N/A，仅 OCR 为 source）** |
| `GET` | `.../ocr-files/{id}/markdown-pages` | **保留**；无 `layout_blocks_json` 时回退库内 markdown；有则现场派生 |

`layout-pages` 每页可选返回：

```json
{
  "page_index": 0,
  "width": 1191,
  "height": 1684,
  "blocks": [ /* LayoutBlockOut */ ],
  "page_raster_url": "https://...",
  "source_markdown": "# Title\n\n...",
  "images": { "img_0": "data:..." }
}
```

`source_markdown` 由 `to_markdown(page_blocks)` 生成，保证与块一致。

### 4.2 文档翻译

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `.../translate/jobs/{id}/layout-pages` | 块含 `translated_text`；每页 `source_markdown` + `translated_markdown` |
| `GET` | `.../translate/jobs/{id}/segments` | 增加 `group_by=page|label|none`（默认 `page`） |
| `GET` | `.../translate/jobs/{id}/download` | `LayoutWriter` 输出 |

---

## 5. 流水线

### 5.1 OCR（Paddle）

1. `layout-parsing` → `from_paddle(prunedResult)` → `LayoutDocument`。
2. 持久化 `layout_blocks_json`、`page_width/height`。
3. PDF/图像：渲染页图 → S3 `page_raster_object_key`。
4. `to_markdown` → 写入 `markdown_text` / `markdown_images`（兼容）。
5. 公式块：`skip_translate` 在 OCR 阶段即标记；markdown 中保持 LaTeX 原样。

### 5.2 翻译

| 格式 | LDM 来源 | 备注 |
|------|----------|------|
| docx / xlsx | 原生抽取 + style_hint | 无页图 |
| pdf 文字层 | PyMuPDF blocks | 可选页图 |
| pdf 扫描 | `ocr_file` layout-pages | `ocr_bridge` 不再仅用 markdown 空行切块 |
| txt / md / csv | 结构块 | md  fenced code 仍单段 |

**翻译循环**：跳过 `skip_translate`；公式块 `translated_text = source_text`。

**assemble**：`LayoutWriter` 消费 `layout_snapshot_json` + segments；PDF OCR 路径为底图 + bbox 叠字。

### 5.3 Celery

状态机不变；`EXTRACTING` 写 `layout_snapshot_json`；`ASSEMBLING` 调用 `LayoutWriter`。

---

## 6. 前端：A / B / C

### 6.1 共享组件

- **`MinervaMarkdown`**（`minerva-ui/src/components/markdown/MinervaMarkdown.tsx`）  
  - 对照区统一 `preset="ocr"`。  
  - `images` 来自页级 `images` map（与 OCR 详情一致）。  
  - 空内容用 `emptyFallback`。

- **`LayoutPageViewer`**（新建）  
  - 底图 + 可选块框 overlay（视觉层）。  
  - **页级对照**：左/右（或上/下）两列各放一个 `MinervaMarkdown`，分别绑定 `source_markdown` 与 `translated_markdown`（来自 `layout-pages` API）。  
  - 非 Markdown 的纯 `skip` 图块仅显示底图区域，不重复渲染 HTML 占位。

### 6.2 A — 可下载

- 行为不变；后端 garantee 与 LDM 一致。扫描 PDF 为「页图 + 定位文字」混合 PDF。

### 6.3 B — 应用内预览

**OCR 任务详情 Drawer**（`FileOcrTaskPage`）：

| Tab | 内容 |
|-----|------|
| 版面预览（默认） | `LayoutPageViewer`：底图 + 块框；页下或侧栏 **单栏 `MinervaMarkdown`（原文）** |
| Markdown | 现有整页 `MinervaMarkdown`（与现网一致，可逐步改为仅展示 `source_markdown`） |

**翻译详情 Modal**：

| Tab | 内容 |
|-----|------|
| 页面对照 | 每页双列 **`MinervaMarkdown`**：左 `source_markdown`，右 `translated_markdown` |
| 版面预览 | `LayoutPageViewer` 双语 overlay（可选二期） |
| 段落对照 | 见 6.4 |

### 6.4 C — 段落对照（Markdown 渲染）

- API：`group_by=page`（默认）→ `groups[].segments[]`。
- UI：按 **页 → label 分组** 折叠；每组内 compare pair：
  - 左：`MinervaMarkdown preset="ocr" markdown={segment.source_text}`
  - 右：`MinervaMarkdown preset="ocr" markdown={segment.translated_text ?? ''}`
- 公式段：左右渲染结果一致（源与译相同字符串）。
- `group_by=none` 保留扁平列表（仍用 Markdown 渲染，非纯文本 `<pre>`）。

**注意**：段内 `source_text` / `translated_text` 应为 **Markdown 片段**（含块内换行、列表、行内公式），由 `to_markdown` 按块生成或块 `source_text` 本身为 markdown 行。

---

## 7. 错误码与配置

沿用 `translate.*`、`file_ocr.*`；新增可选：

| code | 场景 |
|------|------|
| `layout.blocks_missing` | layout-pages 请求时无 LDM |
| `layout.page_raster_missing` | 预览请求页图但 S3 无对象 |

若新增页图存储路径、layout 版本常量，同步 `config.py`、`backend/.env.example`、`backend/.env.dev`。

---

## 8. 测试计划

| 层级 | 内容 |
|------|------|
| 单元 | `labels` 公式 skip；`to_markdown` 公式不变；`overflow` shrink/expand |
| 集成 | Paddle OCR 入库 blocks + markdown 派生一致 |
| 翻译 | 含公式 PDF/MD roundtrip；公式段不调 LLM |
| API | `layout-pages` 双 markdown 字段 |
| 前端 | 段落对照 `MinervaMarkdown` 快照（可选） |

---

## 9. 已确认决策

| 项 | 决策 |
|----|------|
| 架构 | 方案 1：统一 Layout Block 中间层 |
| 排版 | 结构 + 视觉同时实现 |
| 格式 | 全格式（docx/xlsx/pdf/txt/md/csv + 扫描 OCR） |
| 交付 | A 下载 + B 预览 + C 分组对照 |
| 溢出 | 正文/脚注 shrink；标题/表格 expand |
| 公式 | 不机器翻译；保留 LaTeX/Markdown 原样 |
| 对照渲染 | **`MinervaMarkdown` `preset="ocr"`**（页级双栏 + 段落级） |
| 数据库 | 新增字段，无外键 |
| OCR 引擎 | 首期 Paddle 完整实现；MinerU 预留 |

---

## 10. 实现顺序建议

1. `app/layout` 核心 + `ocr_file_*` 字段 + Paddle 持久化 LDM + `to_markdown`。
2. `layout-pages` API + OCR Drawer Tab。
3. 翻译 `extract/assemble` 接 LDM + 公式跳过 + `layout_snapshot`。
4. 翻译详情页级/段落 Markdown 对照 + `LayoutWriter` 下载。
5. 页图渲染与 PDF 写回。
