# PPT Skill 优化设计：参考 ppt-master 的双引擎路线图

**日期**：2026-06-15  
**状态**：Phase 0–4 已实现（2026-06-15）  
**范围**：`backend/app/agent/skills/ppt/` 及关联测试、依赖、SKILL.md  
**参考**：[ppt-master](https://github.com/hugohe3/ppt-master)（MIT）— template-fill 工作流、source_to_md、SVG→PPTX 主流水线  

**关系**：在 `2026-05-20-pptmaker-skill-design.md` 已实现能力之上演进；与 `file` skill 协作（沙箱读写源文件与输出 pptx）；编排见 Agent LangGraph 设计文档。

---

## 1. 背景与动机

Minerva 现有 `ppt` skill（PPT Maker）采用 **内置版式库 + Hybrid 选版 + python-pptx 占位符填充**，已实现 `draft_ppt_outline` 与 `generate_ppt` 双工具流水线，适合快速、低成本生成结构化演示文稿。

[ppt-master](https://github.com/hugohe3/ppt-master) 提供两条可借鉴路径：

| ppt-master 路径 | 特点 |
|-----------------|------|
| **template-fill** | 分析源 PPTX → slide library → fill plan → 容量校验 → OOXML 直接填充；支持备注、切换、表格/图表 |
| **SVG 主流水线** | Strategist → 逐页 SVG → svg_to_pptx；自由设计、视觉上限高，token/耗时成本高 |

本次优化目标（用户确认 **A+B+C+D+E 全量**，**不做 MVP 裁剪**，产出完整路线图 spec）：

| 代号 | 目标 |
|------|------|
| **A** | 生成质量：layout-first 选版、文本容量校验、溢出 warnings |
| **B** | 功能扩展：演讲者备注、页面切换、表格/图表、自定义沙箱模板 |
| **C** | 内容流水线：PDF/DOCX/URL/MD → Markdown → 大纲 → PPT |
| **D** | 视觉上限：SVG 自由设计引擎，输出 natively editable pptx |
| **E** | 工程稳健性：测试矩阵、错误码、可选依赖分层、日志 |

---

## 2. 方案决策

### 2.1 候选方案

| 方案 | 描述 | 结论 |
|------|------|------|
| 1 — 保守演进 | 仅增强现有 layout_fill | ❌ 无法满足 D |
| 2 — 双引擎 | layout_fill + template_fill + svg_design | ✅ **选用** |
| 3 — 子进程包装 | 直接调用 ppt-master 脚本 | ❌ 与沙箱架构耦合差、难测 |

### 2.2 选用方案 2 的理由

- 简单场景保留 **layout_fill 快路径**（低成本、CI 可回归）。
- 用户提供模板时走 **template_fill**（对齐 ppt-master 最强近邻）。
- 高视觉需求走 **svg_design**（满足 D）。
- 三引擎共享沙箱项目契约、校验与测试分层（满足 E）。
- **选择性移植** ppt-master MIT 模块，不引入 git submodule 或 Flask 预览服务（Phase 0–4）。

### 2.3 Strategist 确认方式（svg_design）

采用 **SKILL.md 指引 Agent 在对话中完成设计确认**（类似 ppt-master 八项确认的 BLOCKING 语义），**不**在工具层硬阻塞 API。Agent 须在用户确认 `design_spec` / `spec_lock` 后再调用 `generate_ppt(engine=svg_design)`。

---

## 3. 目标与成功标准

### 3.1 目标

将 Minerva `ppt` skill 升级为 **多引擎 PPT 生成平台**，在 Agent 工作区沙箱内完成：源材料摄入 → 大纲/设计规格 → 三引擎之一生成 → 校验 → 输出 `.pptx`。

### 3.2 成功标准

| 维度 | 验收 |
|------|------|
| **A** | 容量校验覆盖 layout_fill / template_fill；溢出写入 `warnings` 而非静默截断；hybrid + layout-first 选版可解释（`pages[].reason`） |
| **B** | `include_notes=true` 时写入演讲者备注；`transition` 支持 `none` / `fade` / `keep`；template_fill 支持表格/图表 slot 编辑 |
| **C** | `ingest_ppt_source` 支持 PDF、DOCX、XLSX、MD、URL；产物可供 `draft_ppt_outline` 引用 |
| **D** | `engine=svg_design` 输出含 DrawingML 形状的可编辑 pptx；沙箱保留 `svg/` 与 `spec_lock.md` |
| **E** | `backend/tests/test_ppt_*.py` 覆盖三引擎核心路径；`layout_mode=rule` 集成测试无 LLM；错误码与本文 §6 一致 |

### 3.3 向后兼容

- 不传 `engine` 时默认为 `layout_fill`，行为与现网 `generate_ppt` 一致。
- 现有大纲 schema 扩展字段均为可选；旧 outline JSON 无需修改即可生成。

### 3.4 非目标（Phase 0–4）

- 前端 WYSIWYG PPT 编辑器
- 用户模板在线管理 UI（仅沙箱相对路径）
- 独立 REST「生成 PPT」API
- Flask live preview 服务（Phase 5 可选单独立项）
- object-level 入场动画定制、edge-tts 旁白（Phase 5）
- git submodule 方式 vendoring 整个 ppt-master 仓库

---

## 4. 架构

### 4.1 目录结构

```text
backend/app/agent/skills/ppt/
├── SKILL.md
├── tools.py
├── assets/
│   ├── template.pptx
│   └── layout_index.json
├── ingest/                    # 源 → Markdown（移植 source_to_md 子集）
├── pptmaker/                  # 引擎① layout_fill（现有 + 增强）
├── template_fill/             # 引擎②（移植 template_fill_pptx 核心）
├── svg_pipeline/              # 引擎③ svg_design（export + finalize + 编排）
└── shared/                    # schemas、capacity、errors、validate
```

### 4.2 沙箱项目布局

相对工作区根路径（由 Agent 或工具参数 `project_dir` 指定，默认 `ppt/default/`）：

```text
ppt/<project>/
├── sources/           # 原始 PDF/DOCX/MD/用户模板 pptx
├── analysis/          # slide_library.json, fill_plan.json, check_report.json
├── outlines/          # draft.json
├── svg/               # svg_design：page_NN.svg, spec_lock.md, design_spec.md
├── output/            # 最终 .pptx
└── validation/        # 回读 md、校验报告
```

### 4.3 数据流

```text
用户消息 / 源文件（file skill 或 ingest）
  → Planner 路由 ppt
  → [可选] ingest_ppt_source → sources/content.md
  → draft_ppt_outline(brief, source_path?) → outlines/draft.json
  → [template_fill] analyze_ppt_template → slide_library.json
  → [template_fill] check_ppt_fill_plan（可选，推荐）
  → [svg_design] Agent 对话确认 design_spec / spec_lock（SKILL.md BLOCKING）
  → generate_ppt(engine=...) → output/*.pptx
  → [可选] validate_ppt_output
  → 返回 output_path + pages + warnings
```

### 4.4 三引擎对比

| `engine` | 场景 | 实现基础 |
|----------|------|----------|
| `layout_fill`（默认） | 内置版式库、快速生成、CI | 现有 `pptmaker` + 容量 warnings + notes/transition |
| `template_fill` | 用户/内置 pptx 模板，保留原设计 | ppt-master `template_fill_pptx` |
| `svg_design` | 高视觉、自由版式 | ppt-master SVG 流水线（Strategist 产物 + svg_to_pptx） |

---

## 5. 工具契约

由现有 2 个工具扩展为 7 个（`extract_layout_index` 仍为开发脚本，非 Agent 工具）。

### 5.1 `ingest_ppt_source`

| 参数 | 说明 |
|------|------|
| `source_path` | 沙箱内源文件路径（PDF/DOCX/XLSX/MD/TXT） |
| `url` | 与 `source_path` 二选一 |
| `project_dir` | 默认 `ppt/default` |
| `output_md_path` | 默认 `{project_dir}/sources/content.md` |

**返回**：`{ ok, md_path, images_dir, manifest_path, warnings }`

**错误码**：`source_missing`、`unsupported_format`、`convert_failed`、`write_failed`

### 5.2 `draft_ppt_outline`（扩展）

在现有参数基础上增加：

| 参数 | 说明 |
|------|------|
| `source_md_path` | 可选；`ingest` 或用户 MD 路径，作为 brief 补充上下文 |
| `project_dir` | 默认 `ppt/default` |

大纲 slide 可选字段扩展：

| 字段 | 说明 |
|------|------|
| `speakerNotes` | 演讲者备注（layout_fill / template_fill / svg 均可用） |

### 5.3 `analyze_ppt_template`

| 参数 | 说明 |
|------|------|
| `template_path` | 沙箱内 `.pptx` |
| `output_path` | 默认 `{project_dir}/analysis/slide_library.json` |

**返回**：`slide_count`、`page_types` 摘要

**错误码**：`template_missing`、`analyze_failed`

### 5.4 `check_ppt_fill_plan`

| 参数 | 说明 |
|------|------|
| `slide_library_path` | |
| `fill_plan_path` | |
| `output_path` | 默认 `{project_dir}/analysis/check_report.json` |

**返回**：`passed`、`warnings[]`（容量溢出、missing slot 等）

### 5.5 `generate_ppt`（统一出口，扩展）

| 参数 | 说明 |
|------|------|
| `outline` / `outline_path` | 二选一（layout_fill / svg_design 必填；template_fill 可与 fill_plan 并用） |
| `output_path` | 默认 `{project_dir}/output/presentation.pptx` |
| `engine` | `layout_fill` \| `template_fill` \| `svg_design`；默认 `layout_fill` |
| `layout_mode` | `hybrid` \| `rule`；仅 layout_fill |
| `template_path` | template_fill 源 pptx；layout_fill 可选自定义版式库 |
| `fill_plan_path` | template_fill；缺省时 Agent/内部由 outline 生成 |
| `design_spec_path` | svg_design；默认 `{project_dir}/svg/design_spec.md` |
| `spec_lock_path` | svg_design；默认 `{project_dir}/svg/spec_lock.md` |
| `project_dir` | 默认 `ppt/default` |
| `include_notes` | 默认 `true` |
| `transition` | `fade`（默认）\| `none` \| `keep` |

**返回**（与现网兼容并扩展）：

```json
{
  "ok": true,
  "engine": "layout_fill",
  "output_path": "ppt/default/output/presentation.pptx",
  "pages": [],
  "warnings": []
}
```

**错误码**（保留现有 + 新增）：

`outline_invalid`、`template_missing`、`layout_not_found`、`image_load_failed`、`fill_plan_invalid`、`capacity_check_failed`、`svg_export_failed`、`design_spec_missing`、`write_failed`

### 5.6 `validate_ppt_output`

| 参数 | 说明 |
|------|------|
| `pptx_path` | |
| `expected_slide_count` | 可选 |
| `expected_texts` | 可选 string[] |

**返回**：`passed`、`extracted_md_path`、`checks[]`

### 5.7 开发维护

```bash
cd backend
python -m app.agent.skills.ppt.pptmaker.extract_layout_index \
  app/agent/skills/ppt/assets/template.pptx \
  app/agent/skills/ppt/assets/layout_index.json
```

`extract_layout_index` Phase 1 扩展：输出 placeholder `geometry`、`font_size_pt` 估算字段供容量 warnings 使用。

---

## 6. 引擎实现要点

### 6.1 引擎① `layout_fill`

基于现有 `pptmaker/generate.py`：

1. **Hybrid 选版**：保留 `select_layout_hybrid` + 规则兜底（`AI_MIN_CONFIDENCE=0.65`）。
2. **Layout-first 增强**：`layout_index.json` 增加 `contentSignals`、`capacityHints`（由 extract 脚本生成）。
3. **填充后容量检查**：根据 placeholder 宽度与字号估算，超长写入 `warnings`。
4. **speakerNotes**：写入 pptx notes slide。
5. **transition**：生成时写入 OOXML 页面切换（默认 fade；`keep` 不改变模板原值）。

### 6.2 引擎② `template_fill`

对齐 ppt-master [template-fill workflow](https://github.com/hugohe3/ppt-master/blob/main/skills/ppt-master/workflows/template-fill-pptx.md)：

| 步骤 | 模块 |
|------|------|
| analyze | `slide_library.json`：page_type、slots（slot_id、role、geometry、font_size_px）、tables、charts |
| plan | `fill_plan.json`：可复用/重排/省略源页；replacements、table_edits、chart_edits、notes、transition |
| check-plan | 视觉宽度容量校验 |
| apply | 克隆源页 + OOXML 文本/表格/图表替换 + 可达性 prune |

**layout-first 纪律**：输出顺序由目标故事决定，非源 deck 顺序；同一 `source_slide` 可多次出现。

### 6.3 引擎③ `svg_design`

对齐 ppt-master 主流程，适配 Minerva Agent：

| 环节 | 行为 |
|------|------|
| Strategist | Agent 依 SKILL.md 产出 `design_spec.md` + `spec_lock.md`；**对话确认后再 generate** |
| SVG 生成 | Agent 逐页写入 `svg/page_NN.svg`；**禁止**批量脚本生成 SVG（对齐 ppt-master 纪律） |
| spec_lock | 每页生成前 Agent `read_file spec_lock.md`（SKILL.md 强制） |
| 后处理 | `finalize_svg` 等价模块 |
| 导出 | `svg_to_pptx` → natively editable pptx |

**split mode**：长 deck 可在 SKILL.md 指引用户新会话 `继续生成`（对应 ppt-master resume-execute）；实现为 Phase 4 文档约定，不新增 REST。

---

## 7. 内容流水线（ingest）

| 输入 | 依赖 | 输出 |
|------|------|------|
| PDF | PyMuPDF | Markdown + 提取图片 |
| DOCX | mammoth | Markdown + 图片 |
| XLSX/XLSM | openpyxl | Markdown 表格 |
| MD/TXT | 无 | 复制/规范化 |
| URL | requests, beautifulsoup4；可选 curl_cffi | Markdown |

EMF/WMF（Office 矢量图）：ingest 阶段保留原文件；svg 路径导出时按 ppt-master 策略嵌入，不默认转 PNG。

与 `file` skill：用户已上传文件时可跳过 `ingest_ppt_source`，直接传 `source_path` / `outline_path`。

---

## 8. 依赖与环境

### 8.1 pyproject.toml optional extras

```toml
[project.optional-dependencies]
ppt-ingest = ["PyMuPDF>=1.23.0", "mammoth>=1.6.0", "openpyxl>=3.1.0", "markdownify>=0.11.6", "beautifulsoup4>=4.12.0", "requests>=2.31.0"]
ppt-svg = ["cairosvg", "svglib>=1.5.0", "reportlab>=4.0.0", "Pillow>=9.0.0"]
ppt-full = ["minerva[ppt-ingest,ppt-svg]", "edge-tts>=7.2.8", "curl_cffi>=0.7.0"]
```

- 核心：`python-pptx>=1.0.2`（已有）。
- 部署默认不强制 `ppt-full`；CI 至少安装 `ppt-ingest` 用于 ingest 集成测试。

### 8.2 环境变量（若新增）

任何 Settings / `config.py` 新增项须同步 `backend/.env.example` 与 `backend/.env.dev`（例如可选 `PPT_AI_MIN_CONFIDENCE`、`PPT_DEFAULT_TRANSITION`）。

---

## 9. 测试策略（E）

| 层级 | 内容 |
|------|------|
| 单元 | `normalize_slide`、`select_layout_by_rule`、capacity 估算、fill_plan 校验逻辑 |
| 集成 layout_fill | `engine=layout_fill, layout_mode=rule` → pptx 存在、页数、占位符非空 |
| 集成 template_fill | fixture pptx + fill_plan → 关键文本替换正确 |
| 集成 ingest | 小型 PDF/DOCX fixture → md 非空 |
| mock hybrid | mock `chat_model` 返回固定选版 JSON |

测试夹具：`backend/tests/fixtures/ppt/`（小型 pptx、pdf、outline json）。

---

## 10. SKILL.md 与 Planner

### 10.1 路由触发词

保留现有触发词，增加：「从 PDF 做 PPT」「按模板填充」「高质量演示」「自由设计」等。

### 10.2 子 Agent 推荐流程

1. 有源文件 → `ingest_ppt_source` 或确认 `file` 已写入沙箱  
2. `draft_ppt_outline` → 用户可确认 preview  
3. 选择引擎：  
   - 默认 / 快速 → `layout_fill`  
   - 用户提供模板 pptx → `template_fill`（先 `analyze` + 可选 `check`）  
   - 高视觉 / 无固定版式 → `svg_design`（对话确认 design_spec 后 generate）  
4. `validate_ppt_output`（推荐 template_fill / svg_design）  
5. 报告 `output_path`、`pages`、`warnings`

### 10.3 INDEX.md

更新 `ppt` 条目说明三引擎与 ingest 工具。

---

## 11. 分阶段实现路线图

| 阶段 | 内容 | 主要交付 |
|------|------|----------|
| **Phase 0 — E** | 现有路径测试；错误码文档化；`extract_layout_index` geometry 扩展 | CI baseline |
| **Phase 1 — A+B（layout）** | 容量 warnings、speakerNotes、transition；layout_index 增强 | layout_fill 质量 |
| **Phase 2 — C** | `ingest_ppt_source`；`draft_ppt_outline` 读 source md | 文档→PPT |
| **Phase 3 — B（template）** | `template_fill` 模块 + analyze/check/generate 集成 | 自定义模板填充 |
| **Phase 4 — D** | `svg_pipeline` + svg_design + SKILL Strategist 流程 | 高视觉自由设计 |
| **Phase 5 — 可选** | 动画定制、edge-tts、preview API | ppt-master 高级能力 |

每阶段完成后更新本文 **状态** 与 `2026-05-20-pptmaker-skill-design.md` 交叉引用。

---

## 12. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 总体架构 | 双/三引擎 | 兼顾快路径与视觉上限 |
| 引擎命名 | layout_fill / template_fill / svg_design | 用户确认 |
| ppt-master 集成 | 选择性移植 MIT 模块 | 避免 submodule 与 IDE 本地 projects 假设 |
| Strategist 确认 | SKILL.md Agent 对话 BLOCKING | 与 ReAct 一致；用户确认 |
| 默认引擎 | layout_fill | 向后兼容 |
| Live preview | Phase 5 非目标 | 降低 Phase 0–4 复杂度 |
| 测试 | Phase 0 先行 | 满足 E，支撑后续重构 |

---

## 13. 实现清单（供 writing-plans 拆分）

1. Phase 0：测试夹具 + `test_ppt_layout_fill.py` + extract_layout_index geometry  
2. Phase 1：shared/capacity + notes/transition + warnings 通路  
3. Phase 2：`ingest/` + `ingest_ppt_source` + draft 扩展 + optional-deps ppt-ingest  
4. Phase 3：`template_fill/` + analyze/check 工具 + generate 分支  
5. Phase 4：`svg_pipeline/` + design spec 约定 + generate svg_design 分支 + optional-deps ppt-svg  
6. SKILL.md / INDEX.md / 本文状态回填  
7. Phase 5 另开 spec（若需要 preview / 旁白）
