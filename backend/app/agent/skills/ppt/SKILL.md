# ppt（PPT Maker）

根据结构化大纲、源文档或自然语言描述，在**工作区沙箱**内生成可打开的 `.pptx` 演示文稿（PowerPoint / 幻灯片）。支持三引擎：`layout_fill`（内置版式库，默认）、`template_fill`（按用户 pptx 模板填充）、`svg_design`（高视觉 SVG 逐页设计导出）。

## 何时使用

**Planner 必选本 skill（`skill_id=ppt`）**：用户目标是**在本工作区生成新的 `.pptx` 演示文稿**，而不是仅讨论概念、仅读写已有文件，或让模型在对话里「口述幻灯片内容」。

### 应选 `ppt` 的典型场景

| 场景 | 用户可能怎么说 | 本 skill 做什么 |
|------|----------------|-----------------|
| 从零做 deck | 「做一份关于 AI 的 PPT」「帮我写个 10 页幻灯片」「生成演示文稿」 | `draft_ppt_outline` → `generate_ppt` |
| 材料转幻灯片 | 「把这份 PDF/Word/报告做成 PPT」「根据大纲生成 pptx」「文档转演示文稿」 | `ingest_ppt_source` → `draft_ppt_outline` → `generate_ppt` |
| 按模板出稿 | 「用这个 pptx 模板填新内容」「按公司模板做汇报」「模板填充」 | `analyze_ppt_template` → `generate_ppt(engine=template_fill)` |
| 高视觉 / 自由版式 | 「精美 PPT」「高质量演示」「自由设计版式」「像 Keynote 那样排版」 | 确认 `design_spec` 后 `generate_ppt(engine=svg_design)` |

**命中以下任一意图即应选 `ppt`（即使用户未出现「PPT」二字）**：制作/生成/导出/输出/下载 **幻灯片、演示文稿、pptx、PowerPoint、deck、slides、presentation、课件（幻灯片形式）、汇报材料（要 pptx 文件）、路演稿（幻灯片）、述职演示、培训演示**。

### 不要选 `ppt`（避免误路由）

| 用户意图 | 应选 skill | 说明 |
|----------|------------|------|
| 只列出/读取/上传/删除沙箱里的 `.pptx` 或源文件，**不生成新 deck** | `file` | 纯文件操作 |
| 解释 PPT 技巧、点评已有幻灯片、闲聊 | `general` | 无需调用生成工具 |
| 只要 Markdown/Word 报告，**未要求 pptx** | `general` 或对应写作流程 | 不是幻灯片交付物 |

**多步任务**：若需先把 PDF 放入沙箱再生成 PPT，Planner 可拆步（`file` 上传 → `ppt` 生成），但**最终生成 pptx 的一步必须 `skill_id=ppt`**。

**子 Agent 执行**：必须通过 `ingest_ppt_source` / `draft_ppt_outline` / `generate_ppt` 等工具完成，**禁止**编造 `output_path`、版式名称、选版结果或声称已生成但未写入沙箱的 `.pptx`。

### 推荐流程

1. **有 PDF/DOCX/XLSX/MD 等源文件**：先 `ingest_ppt_source(source_path=...)` → 写入 `{project_dir}/sources/content.md`（默认 `ppt/default/sources/content.md`）。
2. **无现成大纲**：`draft_ppt_outline(brief, source_md_path=...)`（可选引用 ingest 产物）→ 大纲写入沙箱（默认 `outlines/draft.json`）→ 可向用户展示 preview。
3. **选择引擎并生成**：
   - **默认 / 快速**：`generate_ppt(outline_path=..., engine=layout_fill)`（Hybrid 选版：LLM 优先，规则兜底）。
   - **用户提供模板 pptx**：`analyze_ppt_template(template_path=...)` → 可选 `check_ppt_fill_plan(...)` → `generate_ppt(engine=template_fill, template_path=..., fill_plan_path=...)`（`fill_plan_path` 可省略，由 outline 自动构建）。
   - **高视觉自由设计**：`engine=svg_design`（见下文 svg_design 工作流；须用户确认 `design_spec` / `spec_lock` 后再 generate）。
4. **配图**：图片须先存在于沙箱（用户上传或 `file` skill 写入）；大纲中 `images[].path` 为沙箱相对路径。
5. **校验（推荐 template_fill）**：`validate_ppt_output(pptx_path=..., expected_slide_count=..., expected_texts=...)`
6. 完成后向用户报告 `output_path`、`pages` 选版/源页摘要及 `warnings`。

## Planner 路由

下列短语为**子串匹配**触发词（用户消息中包含即命中，不区分大小写）。优先理解整体意图：凡要求**产出新的 pptx 文件**，均应选 `ppt`。

### 核心词（中英文）

- ppt
- pptx
- .pptx
- powerpoint
- presentation
- slide deck
- slides
- ppt maker
- keynote（指制作幻灯片时）
- 路演 deck
- 做个 deck

### 制作 / 生成

- 做 ppt
- 做PPT
- 做个ppt
- 做一个ppt
- 写个ppt
- 帮我做ppt
- 帮我生成ppt
- 生成 ppt
- 生成PPT
- 生成 pptx
- 生成幻灯片
- 制作 ppt
- 制作PPT
- 制作幻灯片
- 制作演示文稿
- 生成演示文稿
- 制作 pptx
- 创建演示文稿
- create presentation
- generate slides
- make slides
- make a presentation

### 转化 / 导出

- 做成 ppt
- 做成PPT
- 做成幻灯片
- 做成演示文稿
- 转成 ppt
- 转换为 ppt
- 转成幻灯片
- 文档做 ppt
- 报告做 ppt
- 大纲做 ppt
- 把大纲做成 ppt
- 根据大纲生成幻灯片
- 根据内容做 ppt
- 从 pdf 做 ppt
- pdf转ppt
- PDF转PPT
- 文档转ppt
- 导出演示文稿
- 导出 ppt
- 导出 pptx
- 输出 ppt
- 下载 ppt
- 生成 ppt 文件

### 场景 / 材料

- 演示文稿
- 幻灯片
- 培训课件
- 培训 ppt
- 课件 ppt
- 汇报 ppt
- 工作汇报 ppt
- 述职 ppt
- 路演 ppt
- 提案 ppt
- 方案 ppt
- 答辩 ppt
- 发布会 ppt
- 按模板填充
- 模板填充
- 模板做 ppt
- 高质量演示
- 精美 ppt
- 自由设计
- 从 PDF 做 PPT

## 工具一览

| 工具 | 说明 |
|------|------|
| `ingest_ppt_source` | `source_path` 或 `url` 二选一；`project_dir` 默认 `ppt/default`；写入 `sources/content.md`、提取图片与 `image_manifest.json`。 |
| `analyze_ppt_template` | 分析沙箱内 `.pptx`，输出 `{project_dir}/analysis/slide_library.json`；返回 `slide_count`、`page_types`。 |
| `check_ppt_fill_plan` | 校验 `slide_library.json` 与 `fill_plan.json` 容量与 slot 一致性；写入 `check_report.json`。 |
| `validate_ppt_output` | 回读 pptx，校验页数与关键文本。 |
| `draft_ppt_outline` | `brief` 必填；可选 `slide_count`、`source_md_path`（ingest 或用户 MD）、`output_path`（默认 `outlines/draft.json`）。返回 `path`、`slides_count`、`preview`。 |
| `generate_ppt` | `outline` 或 `outline_path` 二选一（`svg_design` 可无大纲）；`engine` 默认 `layout_fill`；`template_fill` 时传 `template_path`、可选 `fill_plan_path`；`svg_design` 时传 `project_dir`（默认 `ppt/default`）、可选 `design_spec_path` / `spec_lock_path` / `svg_dir`；`layout_mode` 为 `hybrid`（默认）或 `rule`（仅 layout_fill）。返回 `pages`、`warnings`。 |

## 引擎对比

| `engine` | 场景 | 关键参数 |
|----------|------|----------|
| `layout_fill`（默认） | 内置版式库、快速生成 | `layout_mode` |
| `template_fill` | 用户/内置 pptx 模板，保留原设计 | `template_path`, `fill_plan_path` |
| `svg_design` | 高视觉自由版式；Agent 手写逐页 SVG | `project_dir`, `design_spec_path`, `spec_lock_path`, `svg_dir` |

## 大纲 schema（摘要）

```json
{
  "meta": { "title": "封面主标题", "subtitle": "封面副标题" },
  "slides": [
    { "pageTitle": "页标题", "items": [{ "title": "a", "body": "b" }], "speakerNotes": "备注" },
    { "pageTitle": "指标", "keyNumbers": [{ "number": "19", "label": "名称", "desc": "说明" }] },
    { "pageTitle": "配图", "images": [{ "path": "images/a.png", "caption": "说明" }] }
  ]
}
```

## template_fill 数据流

```text
用户模板 pptx（沙箱 sources/）
  → analyze_ppt_template → analysis/slide_library.json
  → [可选] check_ppt_fill_plan（slide_library + fill_plan）
  → generate_ppt(engine=template_fill, outline_path=..., template_path=...)
  → validate_ppt_output
```

`slide_library` schema：`template_fill_pptx_library.v1`（`slides[].slots[]` 含 `slot_id`、`role`、`geometry`、`text_metrics`）。

`fill_plan` schema：`template_fill_pptx_plan.v1`（`slides[].source_slide`、`replacements[]`、`notes`）。

## svg_design 工作流

**禁止**批量调用外部 SVG 生成脚本；由 Agent 在沙箱 `{project_dir}/svg/` 内**逐页编写** `page_01.svg`、`page_02.svg` …（16:9，`viewBox` 建议 `0 0 960 540`）。

1. 与用户确认设计方向，撰写 `{project_dir}/svg/design_spec.md`（版式、配色、字体层级）。
2. 用户明确确认后写入 `{project_dir}/svg/spec_lock.md`（锁定规格，BLOCKING 语义）。
3. Agent 按 spec 手写各页 SVG 到 `svg/` 目录。
4. `generate_ppt(engine=svg_design, project_dir=...)` — 无需 outline，或传最小 `{"slides":[]}`。
5. 可选 `validate_ppt_output` 校验页数与关键文本。

默认路径（`project_dir=ppt/default`）：

- SVG 页：`ppt/default/svg/page_*.svg`
- 设计规格：`ppt/default/svg/design_spec.md`
- 规格锁定：`ppt/default/svg/spec_lock.md`

导出将 SVG 内 `<text>`、`<rect>` 转为可编辑 pptx 形状（16:9，10×5.625 英寸）；复杂矢量可安装可选依赖 `ppt-svg`（svglib/reportlab）。

## 错误码

`ingest_ppt_source`：`source_missing`、`unsupported_format`、`convert_failed`、`write_failed`

`analyze_ppt_template`：`template_missing`、`analyze_failed`、`write_failed`

`check_ppt_fill_plan`：`fill_plan_invalid`、`write_failed`

`draft_ppt_outline`：`invalid_json`、`validation_error`、`write_failed`、`model_unavailable`

`generate_ppt`：`outline_invalid`、`template_missing`、`layout_not_found`、`image_load_failed`、`fill_plan_invalid`、`analyze_failed`、`design_spec_missing`、`svg_export_failed`、`write_failed`

## 版式库维护（开发）

更新 `assets/template.pptx` 后须重建 `assets/layout_index.json`：

```bash
cd backend
python -m app.agent.skills.ppt.pptmaker.extract_layout_index \
  app/agent/skills/ppt/assets/template.pptx \
  app/agent/skills/ppt/assets/layout_index.json
```
