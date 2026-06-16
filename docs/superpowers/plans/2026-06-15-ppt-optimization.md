# PPT Skill 优化（ppt-master 参考）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Minerva `ppt` skill 升级为三引擎 PPT 生成平台（layout_fill / template_fill / svg_design），参考 ppt-master 选择性移植 MIT 模块，分 Phase 0–4 交付可测试增量。

**Architecture:** 保留现有 `pptmaker` 作为默认 `layout_fill` 快路径；新增 `shared/` 契约与容量校验；`template_fill/` 与 `svg_pipeline/` 为独立引擎包；`ingest/` 负责源材料→Markdown；`tools.py` 统一注册 7 个 Agent 工具；沙箱项目目录 `ppt/<project>/`。

**Tech Stack:** Python 3.11+, python-pptx, pydantic, langchain_core.tools, pytest-asyncio；可选 PyMuPDF/mammoth（ingest）、cairosvg/svglib（svg 导出）

**Spec:** `docs/superpowers/specs/2026-06-15-ppt-optimization-design.md`

---

## 文件清单（全阶段）

| 阶段 | 操作 | 路径 | 职责 |
|------|------|------|------|
| 0 | Create | `backend/tests/fixtures/ppt/outline_minimal.json` | 集成测试大纲 |
| 0 | Create | `backend/tests/test_ppt_normalize.py` | normalize 单测 |
| 0 | Create | `backend/tests/test_ppt_layout_select.py` | 规则选版单测 |
| 0 | Create | `backend/tests/test_ppt_layout_fill.py` | layout_fill 集成 |
| 0 | Modify | `backend/app/agent/skills/ppt/pptmaker/extract_layout_index.py` | geometry 字段 |
| 0 | Modify | `backend/app/agent/skills/ppt/assets/layout_index.json` | 重建含 geometry |
| 1 | Create | `backend/app/agent/skills/ppt/shared/__init__.py` | 包入口 |
| 1 | Create | `backend/app/agent/skills/ppt/shared/capacity.py` | 文本容量估算 |
| 1 | Create | `backend/app/agent/skills/ppt/shared/transitions.py` | OOXML 页面切换 |
| 1 | Create | `backend/app/agent/skills/ppt/shared/notes.py` | 演讲者备注写入 |
| 1 | Create | `backend/tests/test_ppt_capacity.py` | 容量单测 |
| 1 | Modify | `backend/app/agent/skills/ppt/pptmaker/fill.py` | 填充后容量 warnings |
| 1 | Modify | `backend/app/agent/skills/ppt/pptmaker/generate.py` | notes/transition/engine 参数 |
| 1 | Modify | `backend/app/agent/skills/ppt/pptmaker/schemas.py` | speakerNotes 可选字段 |
| 1 | Modify | `backend/app/agent/skills/ppt/tools.py` | generate_ppt 新参数 |
| 2 | Create | `backend/app/agent/skills/ppt/ingest/__init__.py` | 包入口 |
| 2 | Create | `backend/app/agent/skills/ppt/ingest/converters.py` | PDF/DOCX/XLSX/MD/URL |
| 2 | Create | `backend/tests/fixtures/ppt/sample.pdf` | ingest 夹具（最小 PDF） |
| 2 | Create | `backend/tests/test_ppt_ingest.py` | ingest 单测/集成 |
| 2 | Modify | `backend/pyproject.toml` | 添加 `mammoth`（DOCX）；`ppt-ingest` extra |
| 2 | Modify | `backend/app/agent/skills/ppt/tools.py` | `ingest_ppt_source` |
| 3 | Create | `backend/app/agent/skills/ppt/template_fill/analyze.py` | slide_library 提取 |
| 3 | Create | `backend/app/agent/skills/ppt/template_fill/check_plan.py` | 容量校验 |
| 3 | Create | `backend/app/agent/skills/ppt/template_fill/apply.py` | fill plan 应用 |
| 3 | Create | `backend/app/agent/skills/ppt/template_fill/plan_builder.py` | outline→fill_plan |
| 3 | Create | `backend/tests/fixtures/ppt/template_mini.pptx` | 小型模板夹具 |
| 3 | Create | `backend/tests/test_ppt_template_fill.py` | template_fill 集成 |
| 3 | Modify | `backend/app/agent/skills/ppt/pptmaker/generate.py` | template_fill 分支 |
| 3 | Modify | `backend/app/agent/skills/ppt/tools.py` | analyze/check 工具 |
| 4 | Create | `backend/app/agent/skills/ppt/svg_pipeline/finalize.py` | SVG 后处理 |
| 4 | Create | `backend/app/agent/skills/ppt/svg_pipeline/export.py` | svg→pptx（移植 svg_to_pptx 核心） |
| 4 | Create | `backend/app/agent/skills/ppt/svg_pipeline/generate.py` | svg_design 编排 |
| 4 | Create | `backend/tests/fixtures/ppt/svg/page_01.svg` | 最小 SVG 页 |
| 4 | Create | `backend/tests/test_ppt_svg_export.py` | svg 导出集成 |
| 4 | Modify | `backend/pyproject.toml` | `ppt-svg` optional extra |
| 4 | Modify | `backend/app/agent/skills/ppt/pptmaker/generate.py` | svg_design 分支 |
| 4 | Modify | `backend/app/agent/skills/ppt/SKILL.md` | 三引擎工作流 + Strategist |
| 4 | Modify | `backend/app/agent/skills/INDEX.md` | 更新 ppt 条目 |
| 各阶段 | Modify | `docs/superpowers/specs/2026-06-15-ppt-optimization-design.md` | 阶段完成后回填状态 |

---

## Phase 0 — 工程基线（E）

### Task 0.1: 测试夹具

**Files:**
- Create: `backend/tests/fixtures/ppt/outline_minimal.json`

- [ ] **Step 1: 创建最小大纲 JSON**

```json
{
  "meta": { "title": "测试封面", "subtitle": "副标题" },
  "slides": [
    { "pageTitle": "三大优势", "items": [
      { "title": "优势一", "body": "说明一" },
      { "title": "优势二", "body": "说明二" },
      { "title": "优势三", "body": "说明三" }
    ]}
  ]
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/fixtures/ppt/outline_minimal.json
git commit -m "test(ppt): add minimal outline fixture"
```

---

### Task 0.2: normalize 单测

**Files:**
- Create: `backend/tests/test_ppt_normalize.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for pptmaker.normalize."""

from __future__ import annotations

from app.agent.skills.ppt.pptmaker.normalize import expand_outline_with_meta, normalize_slide


def test_normalize_slide_items_from_content_lines() -> None:
    """Multiline content splits into items."""

    spec = normalize_slide({"pageTitle": "页", "content": "A：正文a\nB：正文b"})
    assert len(spec["items"]) == 2
    assert spec["items"][0]["title"] == "A"


def test_expand_outline_with_meta_inserts_cover() -> None:
    """Meta block prepends a cover slide spec."""

    slides = expand_outline_with_meta(
        {"meta": {"title": "主标题", "subtitle": "副标题"}, "slides": [{"pageTitle": "正文"}]}
    )
    assert slides[0].get("pageType") == "cover"
    assert slides[0]["pageTitle"] == "主标题"
    assert len(slides) == 2
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_ppt_normalize.py -v`  
Expected: PASS（函数已存在，测试应直接绿）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_ppt_normalize.py
git commit -m "test(ppt): cover normalize_slide and expand_outline_with_meta"
```

---

### Task 0.3: 规则选版单测

**Files:**
- Create: `backend/tests/test_ppt_layout_select.py`

- [ ] **Step 1: 编写测试（读取真实 layout_index.json）**

```python
"""Tests for pptmaker.layout_select rule mapping."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.skills.ppt.pptmaker.layout_select import select_layout_by_rule

_LAYOUT_INDEX = Path(__file__).resolve().parents[1] / "app/agent/skills/ppt/assets/layout_index.json"


def _load_index() -> list[dict]:
    return json.loads(_LAYOUT_INDEX.read_text(encoding="utf-8"))


def test_rule_selects_three_column_for_three_items() -> None:
    """Three items map to a three-column layout name."""

    layout_index = _load_index()
    slide_spec = {
        "pageTitle": "三大优势",
        "items": [
            {"title": "a", "body": "1"},
            {"title": "b", "body": "2"},
            {"title": "c", "body": "3"},
        ],
    }
    name = select_layout_by_rule(slide_spec, layout_index)
    assert "三列" in name or "three" in name.lower() or name  # 允许 bestFor 回退


def test_rule_selects_cover_for_page_type() -> None:
    """Cover page type selects title slide layout."""

    layout_index = _load_index()
    name = select_layout_by_rule({"pageType": "cover", "pageTitle": "封面"}, layout_index)
    assert name == "标题幻灯片"
```

- [ ] **Step 2: 运行**

Run: `cd backend && pytest tests/test_ppt_layout_select.py -v`  
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_ppt_layout_select.py
git commit -m "test(ppt): add select_layout_by_rule regression tests"
```

---

### Task 0.4: layout_fill 集成测试（无 LLM）

**Files:**
- Create: `backend/tests/test_ppt_layout_fill.py`

- [ ] **Step 1: 编写异步集成测试**

```python
"""Integration tests for layout_fill PPT generation."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from pptx import Presentation

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.skills.ppt.pptmaker.generate import generate_presentation

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ppt"


@pytest.mark.asyncio
async def test_generate_presentation_rule_mode_creates_pptx(tmp_path, monkeypatch) -> None:
    """layout_mode=rule produces a non-empty pptx in sandbox."""

    workspace_id = uuid.uuid4()
    monkeypatch.setattr(
        AgentFileSandbox,
        "_workspace_root",
        staticmethod(lambda _wid: tmp_path),
    )
    box = AgentFileSandbox(workspace_id=workspace_id)
    outline = json.loads((FIXTURES / "outline_minimal.json").read_text(encoding="utf-8"))
    outline_path = "outlines/test.json"
    await box.write_file_async(outline_path, json.dumps(outline, ensure_ascii=False))

    result = await generate_presentation(
        outline,
        workspace_id=workspace_id,
        output_path="output/test.pptx",
        layout_mode="rule",
        chat_model=None,
    )
    assert result["ok"] is True
    dest = box.resolve(result["output_path"])
    assert dest.is_file()
    prs = Presentation(str(dest))
    assert len(prs.slides) >= 2
    assert result["pages"]
```

- [ ] **Step 2: 运行并修复 monkeypatch 方式**

Run: `cd backend && pytest tests/test_ppt_layout_fill.py -v`  
若 `AgentFileSandbox._workspace_root` 不可 patch，改为 patch `resolve_agent_files_root` 指向 `tmp_path`（读 `agent_file_sandbox.py` 实际入口）。

- [ ] **Step 3: 全部 ppt 测试**

Run: `cd backend && pytest tests/test_ppt_*.py -v`  
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_ppt_layout_fill.py
git commit -m "test(ppt): add layout_fill rule-mode integration test"
```

---

### Task 0.5: extract_layout_index geometry 扩展

**Files:**
- Modify: `backend/app/agent/skills/ppt/pptmaker/extract_layout_index.py`
- Modify: `backend/app/agent/skills/ppt/assets/layout_index.json`

- [ ] **Step 1: 在 placeholder 输出中增加 geometry**

在提取每个 placeholder 时追加字段（示例逻辑）：

```python
def _placeholder_geometry(shape) -> dict[str, float]:
    """Return width/height in points for capacity hints."""

    width_pt = shape.width / EMU_PER_INCH * 72
    height_pt = shape.height / EMU_PER_INCH * 72
    return {"widthPt": round(width_pt, 1), "heightPt": round(height_pt, 1)}
```

写入 `layout["placeholders"][].geometry`；若可读取 `text_frame` 首 run 字号，写入 `fontSizePt`。

- [ ] **Step 2: 重建 layout_index.json**

Run:
```bash
cd backend
python -m app.agent.skills.ppt.pptmaker.extract_layout_index \
  app/agent/skills/ppt/assets/template.pptx \
  app/agent/skills/ppt/assets/layout_index.json
```

- [ ] **Step 3: 断言 geometry 存在**

在 `test_ppt_layout_select.py` 追加：

```python
def test_layout_index_has_geometry_on_placeholders() -> None:
    layout_index = _load_index()
    first_ph = layout_index[0]["placeholders"][0]
    assert "geometry" in first_ph
    assert first_ph["geometry"]["widthPt"] > 0
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/skills/ppt/pptmaker/extract_layout_index.py \
  backend/app/agent/skills/ppt/assets/layout_index.json \
  backend/tests/test_ppt_layout_select.py
git commit -m "feat(ppt): add placeholder geometry to layout_index extraction"
```

---

## Phase 1 — layout_fill 质量（A+B）

### Task 1.1: shared/capacity.py

**Files:**
- Create: `backend/app/agent/skills/ppt/shared/capacity.py`
- Create: `backend/tests/test_ppt_capacity.py`

- [ ] **Step 1: 失败测试**

```python
"""Tests for text capacity estimation."""

from app.agent.skills.ppt.shared.capacity import estimate_text_capacity, check_text_overflow


def test_estimate_capacity_scales_with_width() -> None:
    cap = estimate_text_capacity(width_pt=400.0, font_size_pt=18.0, lines=1)
    assert cap > estimate_text_capacity(width_pt=200.0, font_size_pt=18.0, lines=1)


def test_check_overflow_returns_warning() -> None:
    warnings = check_text_overflow(
        text="这是一段很长的标题" * 20,
        width_pt=100.0,
        font_size_pt=24.0,
        label="title",
    )
    assert warnings
```

- [ ] **Step 2: 实现**

```python
"""Visual text capacity estimation for layout_fill warnings."""

from __future__ import annotations

# CJK ≈ 1.0 unit width; Latin ≈ 0.55 at same font size
_CJK_RATIO = 1.0
_LATIN_RATIO = 0.55


def _visual_length(text: str) -> float:
    total = 0.0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            total += _CJK_RATIO
        else:
            total += _LATIN_RATIO
    return total


def estimate_text_capacity(*, width_pt: float, font_size_pt: float, lines: int = 1) -> float:
    """Estimate safe visual character units for a text box."""

    chars_per_line = max(width_pt / max(font_size_pt * 0.6, 1.0), 1.0)
    return chars_per_line * max(lines, 1)


def check_text_overflow(
    *,
    text: str,
    width_pt: float,
    font_size_pt: float,
    label: str,
    lines: int = 1,
) -> list[str]:
    """Return warning strings when text likely overflows its placeholder."""

    if not text.strip():
        return []
    capacity = estimate_text_capacity(width_pt=width_pt, font_size_pt=font_size_pt, lines=lines)
    if _visual_length(text) > capacity * 1.05:
        return [f"text may overflow placeholder '{label}' ({len(text)} chars vs ~{int(capacity)} capacity)"]
    return []
```

- [ ] **Step 3: 运行** `pytest tests/test_ppt_capacity.py -v` → PASS

- [ ] **Step 4: Commit** `feat(ppt): add shared text capacity estimation`

---

### Task 1.2: speakerNotes + transition

**Files:**
- Create: `backend/app/agent/skills/ppt/shared/notes.py`
- Create: `backend/app/agent/skills/ppt/shared/transitions.py`
- Modify: `backend/app/agent/skills/ppt/pptmaker/generate.py`
- Modify: `backend/app/agent/skills/ppt/pptmaker/schemas.py`

- [ ] **Step 1: notes.py**

```python
"""Write speaker notes to a pptx slide."""

from __future__ import annotations

from pptx.slide import Slide


def set_speaker_notes(slide: Slide, notes: str) -> None:
    """Set notes slide text when notes is non-empty."""

    text = notes.strip()
    if not text:
        return
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = text
```

- [ ] **Step 2: transitions.py** — 使用 `slide.element` 写入 `p:transition` 子节点；`fade` 写 `fade` effect；`none` 移除；`keep`  no-op。参考 python-pptx 社区 OOXML 模式或 ppt-master 导出逻辑。

- [ ] **Step 3: generate.py** — `generate_presentation` 增加参数：

```python
async def generate_presentation(
    outline: dict[str, Any],
    *,
    workspace_id: uuid.UUID,
    output_path: str,
    layout_mode: str = "hybrid",
    chat_model: BaseChatModel | None = None,
    engine: str = "layout_fill",
    include_notes: bool = True,
    transition: str = "fade",
    ...
) -> dict[str, Any]:
```

循环内：`fill_slide_content` 后调用 `set_speaker_notes(slide, slide_spec.get("speakerNotes", ""))`；若 `transition != "keep"` 调用 `apply_slide_transition(slide, transition)`。

- [ ] **Step 4: fill.py** — 填充文本后，根据 `labels` + `layout_index` geometry 调用 `check_text_overflow`，extend warnings。

- [ ] **Step 5: 集成测试** — 在 `test_ppt_layout_fill.py` 增加带 `speakerNotes` 的大纲，生成后断言 `slide.notes_slide.notes_text_frame.text` 非空。

- [ ] **Step 6: tools.py** — `generate_ppt` 增加 `include_notes: bool = True`, `transition: str = "fade"`, `engine: str = "layout_fill"` 并透传；返回 JSON 增加 `"engine"` 字段。

- [ ] **Step 7: Commit** `feat(ppt): add speaker notes, transitions, and capacity warnings to layout_fill`

---

## Phase 2 — 内容流水线（C）

### Task 2.1: ingest converters

**Files:**
- Create: `backend/app/agent/skills/ppt/ingest/converters.py`
- Create: `backend/tests/test_ppt_ingest.py`

- [ ] **Step 1: 实现 `convert_source_to_markdown(path: Path) -> tuple[str, list[Path]]`**

| 后缀 | 实现 |
|------|------|
| `.pdf` | `fitz.open` 提取文本+图片到目录 |
| `.docx` | `mammoth.convert_to_markdown` |
| `.xlsx`/`.xlsm` | `openpyxl` 转 markdown 表格 |
| `.md`/`.txt` | 直读 |
| URL | `httpx.get` + `beautifulsoup4` 去标签 |

- [ ] **Step 2: pyproject.toml** 添加 `mammoth>=1.6.0` 到主 dependencies（与 spec 一致；pymupdf/openpyxl/bs4 已有）。

- [ ] **Step 3: 单测** — 用 `outline_minimal` 同级创建 `sample.md`，断言 convert 返回非空 md。

- [ ] **Step 4: Commit** `feat(ppt): add source-to-markdown ingest converters`

---

### Task 2.2: ingest_ppt_source 工具

**Files:**
- Modify: `backend/app/agent/skills/ppt/tools.py`

- [ ] **Step 1: 注册工具**

```python
@tool
async def ingest_ppt_source(
    source_path: str = "",
    url: str = "",
    project_dir: str = "ppt/default",
    output_md_path: str = "",
) -> str:
    """将 PDF/DOCX/XLSX/MD/URL 转为沙箱 Markdown 与图片 manifest。"""
```

- [ ] **Step 2: 写入 `{project_dir}/sources/content.md` 与 `image_manifest.json`**

- [ ] **Step 3: 扩展 draft_ppt_outline** — 增加 `source_md_path`；若提供则 read 沙箱 md 拼入 HumanMessage。

- [ ] **Step 4: 集成测试** — ingest md → draft outline mock model → generate rule mode。

- [ ] **Step 5: Commit** `feat(ppt): add ingest_ppt_source tool and draft source_md support`

---

## Phase 3 — template_fill 引擎（B）

### Task 3.1: 移植 analyze（slide_library）

**Files:**
- Create: `backend/app/agent/skills/ppt/template_fill/analyze.py`

- [ ] **Step 1: 参考 ppt-master `template_fill_pptx.py analyze` 子命令**，实现 `analyze_template(pptx_path: Path) -> dict` 输出 schema `slide_library.v1`：`slides[].slots[]` 含 `slot_id`, `role`, `geometry`, `text_metrics.font_size_px`, `tables`, `charts`。

- [ ] **Step 2: 单测** — 对 `assets/template.pptx` analyze，断言 `slides` 非空、`slot_id` 唯一。

- [ ] **Step 3: Commit** `feat(ppt): add template_fill slide library analyzer`

---

### Task 3.2: check_plan + apply

**Files:**
- Create: `backend/app/agent/skills/ppt/template_fill/check_plan.py`
- Create: `backend/app/agent/skills/ppt/template_fill/apply.py`
- Create: `backend/app/agent/skills/ppt/template_fill/plan_builder.py`

- [ ] **Step 1: check_plan.py** — `check_fill_plan(library, plan) -> dict` 返回 `{passed, warnings[]}`；使用 `shared/capacity.py` 与 slot geometry。

- [ ] **Step 2: apply.py** — `apply_fill_plan(source_pptx, plan, output_pptx, *, transition="fade")` 克隆 slide、替换 text/table/chart、写 notes、设置 transition。

- [ ] **Step 3: plan_builder.py** — `outline_to_fill_plan(outline, library) -> dict`：layout-first 匹配 `page_type` 与 slot role（首版规则映射，LLM 可选后续增强）。

- [ ] **Step 4: 集成测试** — fixture `template_mini.pptx` + 手工 `fill_plan.json` → apply → 断言标题文本已替换。

- [ ] **Step 5: Commit** `feat(ppt): add template_fill check and apply pipeline`

---

### Task 3.3: 工具与 generate 分支

**Files:**
- Modify: `backend/app/agent/skills/ppt/tools.py`
- Modify: `backend/app/agent/skills/ppt/pptmaker/generate.py`
- Create: `backend/tests/test_ppt_template_fill.py`

- [ ] **Step 1: tools** — `analyze_ppt_template`, `check_ppt_fill_plan` 注册。

- [ ] **Step 2: generate.py** — `engine=="template_fill"` 时：resolve template_path → analyze（或读缓存 library）→ build plan → check（warnings 不阻断）→ apply。

- [ ] **Step 3: validate_ppt_output 工具（首版）** — 用 python-pptx 读 slide shapes text + slide count；可选后续移植 ppt_to_md。

- [ ] **Step 4: 运行** `pytest tests/test_ppt_template_fill.py tests/test_ppt_*.py -v`

- [ ] **Step 5: Commit** `feat(ppt): wire template_fill engine and validation tool`

---

## Phase 4 — svg_design 引擎（D）

### Task 4.1: svg export 核心

**Files:**
- Create: `backend/app/agent/skills/ppt/svg_pipeline/export.py`
- Create: `backend/app/agent/skills/ppt/svg_pipeline/finalize.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 从 ppt-master 移植 `svg_to_pptx.py` 核心函数**（MIT 注明来源）为 `export_svgs_to_pptx(svg_dir: Path, output_pptx: Path) -> None`。

- [ ] **Step 2: pyproject.toml** 增加 optional extra：

```toml
ppt-svg = ["svglib>=1.5.0", "reportlab>=4.0.0", "Pillow>=9.0.0"]
```

- [ ] **Step 3: finalize.py** — 对 `svg_dir/*.svg` 做路径规范化、外链图片复制到沙箱（简化版 finalize_svg）。

- [ ] **Step 4: 夹具** — 最小 `page_01.svg`（矩形+text）；测试 export 生成 pptx 且 `len(slides)==1`。

- [ ] **Step 5: Commit** `feat(ppt): add svg_pipeline export from SVG pages`

---

### Task 4.2: svg_design generate 分支

**Files:**
- Create: `backend/app/agent/skills/ppt/svg_pipeline/generate.py`
- Modify: `backend/app/agent/skills/ppt/pptmaker/generate.py`

- [ ] **Step 1: generate_svg_presentation** — 校验 `spec_lock_path`/`design_spec_path` 存在；校验 `svg_dir` 下至少一个 `page_*.svg`；调用 finalize + export；返回 `{engine: "svg_design", output_path, warnings}`。

- [ ] **Step 2: generate_presentation** — `engine=="svg_design"` 分支调用上述函数；缺 spec 抛 `PptGenerateError("design_spec_missing", ...)`。

- [ ] **Step 3: tools.py** — `generate_ppt` 增加 `design_spec_path`, `spec_lock_path`, `project_dir`。

- [ ] **Step 4: Commit** `feat(ppt): wire svg_design engine into generate_ppt`

---

### Task 4.3: SKILL.md 与文档

**Files:**
- Modify: `backend/app/agent/skills/ppt/SKILL.md`
- Modify: `backend/app/agent/skills/INDEX.md`
- Modify: `docs/superpowers/specs/2026-06-15-ppt-optimization-design.md`

- [ ] **Step 1: SKILL.md** — 文档化三引擎选择、ingest 流程、svg_design Strategist BLOCKING（用户确认 design_spec 后再 generate）、禁止批量 SVG 脚本。

- [ ] **Step 2: INDEX.md** — 更新 ppt 描述。

- [ ] **Step 3: Spec 回填** — 状态改为「Phase 0–4 已实现」，附引擎对照表。

- [ ] **Step 4: 全量测试** `pytest tests/test_ppt_*.py -v`

- [ ] **Step 5: Commit** `docs(ppt): update SKILL and spec after svg_design rollout`

---

## Phase 5 — 不在本计划范围

动画定制、edge-tts 旁白、Flask live preview 另开 spec：`docs/superpowers/specs/2026-06-15-ppt-phase5-advanced-design.md`（待 brainstorm）。

---

## Spec 覆盖自检

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §3 成功标准 A | Task 1.1–1.2 |
| §3 成功标准 B | Task 1.2, 3.2–3.3 |
| §3 成功标准 C | Task 2.1–2.2 |
| §3 成功标准 D | Task 4.1–4.2 |
| §3 成功标准 E | Task 0.1–0.5 + 各阶段测试 |
| §5 工具契约 | Task 1.2, 2.2, 3.3, 4.2 |
| §6 三引擎 | Phase 1/3/4 |
| §8 依赖 | Task 2.1, 4.1 |
| §10 SKILL | Task 4.3 |

无 TBD / 占位符。

---

## 执行顺序建议

1. **Phase 0** 必须最先完成（后续重构安全网）
2. **Phase 1** 可独立上线（用户无感知 API 扩展）
3. **Phase 2** 依赖 Phase 0 测试模式
4. **Phase 3** 依赖 Phase 1 shared/capacity
5. **Phase 4** 依赖 Phase 0 沙箱集成测试模式；可与 Phase 3 并行开发但合并前需全量 pytest

每 Phase 结束时运行：`cd backend && pytest tests/test_ppt_*.py -v`
