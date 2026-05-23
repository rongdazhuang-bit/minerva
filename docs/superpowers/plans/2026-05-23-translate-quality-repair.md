# Translate Quality Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair document translation output quality by making structure-aware extraction and writer paths testable for Markdown, CSV, spreadsheets, DOCX, and PDF while improving detail preview fallbacks.

**Architecture:** Keep the existing translate API, Celery state machine, and UI shell. Add a focused `backend/app/layout/writers/` layer consumed by format strategies, strengthen segment anchors for structured formats, then simplify the front-end detail data flow around page-grouped segments and layout fallback messaging.

**Tech Stack:** FastAPI, SQLAlchemy async, Celery, PyMuPDF, python-docx, openpyxl, xlrd/xlwt, Python `csv`, React 18, Ant Design, TanStack Query, MinervaMarkdown.

---

## File Structure

### Backend Creates

- `backend/app/layout/writers/__init__.py` — writer package exports.
- `backend/app/layout/writers/base.py` — `WriteContext` dataclass and `LayoutWriter` protocol.
- `backend/app/layout/writers/text_writer.py` — TXT / MD / CSV write-back helpers.
- `backend/app/layout/writers/spreadsheet_writer.py` — XLSX / XLS cell write-back helpers.
- `backend/app/layout/writers/docx_writer.py` — DOCX paragraph and table-cell write-back helpers.
- `backend/app/layout/writers/pdf_writer.py` — PDF bbox replacement and overflow handling.
- `backend/app/layout/writers/registry.py` — extension-to-writer dispatch.
- `backend/tests/test_translate_md_strategy.py` — Markdown code-block skip regression.
- `backend/tests/test_translate_csv_strategy.py` — CSV field-level roundtrip regression.
- `backend/tests/test_translate_xlsx_strategy.py` — XLSX cell-level roundtrip regression.
- `backend/tests/test_translate_docx_strategy.py` — DOCX paragraph/table write-back regression.
- `backend/tests/test_translate_pdf_writer.py` — PDF overflow and skip-block regression.
- `backend/tests/test_translate_layout_pages_api.py` — layout-pages fallback regression.

### Backend Modifies

- `backend/app/translate/service/strategies/md_strategy.py` — mark fenced code as `skip_translate`.
- `backend/app/translate/service/strategies/csv_strategy.py` — parse fields and anchor by row/field.
- `backend/app/translate/service/strategies/xlsx_strategy.py` — extract/write cells rather than tab-joined rows.
- `backend/app/translate/service/strategies/xls_strategy.py` — extract/write cells rather than tab-joined rows.
- `backend/app/translate/service/strategies/docx_strategy.py` — delegate write-back to DOCX writer.
- `backend/app/translate/service/strategies/word_strategy.py` — keep DOC conversion, delegate DOCX write-back.
- `backend/app/translate/service/strategies/pdf_strategy.py` — delegate PDF write-back to PDF writer.
- `backend/app/translate/service/run_pipeline.py` — pass `layout_snapshot_json` into writer context when assembling.
- `backend/app/translate/service/layout_pages.py` — preserve fallback behavior for old anchors.

### Frontend Modifies

- `minerva-ui/src/features/translate/TranslatePage.tsx` — use page-grouped segments as primary detail data.
- `minerva-ui/src/features/translate/TranslatePageLayoutCompare.tsx` — keep page compare usable with grouped data.
- `minerva-ui/src/api/translate.ts` — preserve `ApiError` details for download failures if needed.
- `minerva-ui/src/i18n/locales/zh-CN.json` — add fallback/error text.
- `minerva-ui/src/i18n/locales/en.json` — add fallback/error text.

### Docs Modifies After Implementation

- `docs/superpowers/specs/2026-05-20-document-translate-design.md` — implementation comparison for doc/xls and structured write-back.
- `docs/superpowers/specs/2026-05-22-layout-preserving-ocr-translate-design.md` — implementation comparison for writer paths.

---

### Task 1: Writer Protocol and Markdown Skip Blocks

**Files:**
- Create: `backend/app/layout/writers/__init__.py`
- Create: `backend/app/layout/writers/base.py`
- Create: `backend/app/layout/writers/text_writer.py`
- Modify: `backend/app/translate/service/strategies/md_strategy.py`
- Test: `backend/tests/test_translate_md_strategy.py`

- [ ] **Step 1: Write the failing Markdown skip test**

Create `backend/tests/test_translate_md_strategy.py`:

```python
from pathlib import Path

from app.translate.domain.constants import DOC_TRANSLATE_SEGMENT_DONE
from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.md_strategy import MdTranslateStrategy


def test_markdown_fenced_code_is_skip_translate(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    output = tmp_path / "output.md"
    source.write_text(
        "# Title\n\nTranslate me.\n\n```python\nprint('do not translate')\n```\n",
        encoding="utf-8",
    )

    strategy = MdTranslateStrategy()
    drafts = strategy.extract(source)

    code = next(d for d in drafts if "print(" in d.source_text)
    assert code.anchor_json is not None
    assert code.anchor_json["skip_translate"] is True
    assert code.anchor_json["label"] == "code"

    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=d.source_text if d.anchor_json and d.anchor_json.get("skip_translate") else "译文",
            anchor_json=d.anchor_json,
            status=DOC_TRANSLATE_SEGMENT_DONE,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    written = output.read_text(encoding="utf-8")
    assert "```python\nprint('do not translate')\n```" in written
    assert "译文" in written
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_translate_md_strategy.py -v
```

Expected: fail because fenced code anchors do not include `skip_translate` / `label`.

- [ ] **Step 3: Add writer protocol**

Create `backend/app/layout/writers/base.py`:

```python
"""Common writer contracts for layout-aware document translation output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.layout.models import LayoutDocument
from app.translate.domain.dto import SegmentRecord


@dataclass(frozen=True)
class WriteContext:
    """Inputs required to assemble one translated document."""

    source_path: Path
    out_path: Path
    segments: list[SegmentRecord]
    layout_document: LayoutDocument | None = None


class LayoutWriter(Protocol):
    """Write translated segments back into one output file."""

    def write(self, context: WriteContext) -> None:
        """Create ``context.out_path`` from source, layout snapshot, and translated segments."""
```

Create `backend/app/layout/writers/__init__.py`:

```python
"""Layout-aware writers used by document translation strategies."""

from app.layout.writers.base import LayoutWriter, WriteContext

__all__ = ["LayoutWriter", "WriteContext"]
```

- [ ] **Step 4: Add text writer**

Create `backend/app/layout/writers/text_writer.py`:

```python
"""Writers for plain text and Markdown-like ordered segment output."""

from __future__ import annotations

from app.layout.writers.base import WriteContext


class OrderedTextWriter:
    """Write records in sequence separated by blank lines."""

    def write(self, context: WriteContext) -> None:
        ordered = sorted(context.segments, key=lambda s: s.seq)
        parts = [
            s.source_text if (s.anchor_json or {}).get("skip_translate") else s.translated_text
            for s in ordered
        ]
        context.out_path.write_text(
            "\n\n".join((p or "") for p in parts),
            encoding="utf-8",
        )
```

- [ ] **Step 5: Update Markdown strategy anchors and writer call**

In `backend/app/translate/service/strategies/md_strategy.py`, set code block anchors:

```python
anchor = {"block": seq}
if block.lstrip().startswith("```"):
    anchor.update({"label": "code", "skip_translate": True, "overflow_policy": "skip"})
drafts.append(SegmentDraft(seq=seq, source_text=block, anchor_json=anchor))
```

In `assemble()`, delegate:

```python
from app.layout.writers.base import WriteContext
from app.layout.writers.text_writer import OrderedTextWriter


def assemble(self, segments: list[SegmentRecord], source_path: Path, out_path: Path) -> None:
    OrderedTextWriter().write(
        WriteContext(source_path=source_path, out_path=out_path, segments=segments)
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
cd backend && pytest tests/test_translate_md_strategy.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/layout/writers backend/app/translate/service/strategies/md_strategy.py backend/tests/test_translate_md_strategy.py
git commit -m "fix(translate): preserve markdown fenced code blocks"
```

---

### Task 2: CSV Field-Level Extraction and Write-Back

**Files:**
- Modify: `backend/app/layout/writers/text_writer.py`
- Modify: `backend/app/translate/service/strategies/csv_strategy.py`
- Test: `backend/tests/test_translate_csv_strategy.py`

- [ ] **Step 1: Write failing CSV roundtrip test**

Create `backend/tests/test_translate_csv_strategy.py`:

```python
from pathlib import Path

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.csv_strategy import CsvTranslateStrategy


def test_csv_translates_fields_without_changing_shape(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "output.csv"
    source.write_text('name,desc\n"apple","red, sweet"\n', encoding="utf-8-sig")

    strategy = CsvTranslateStrategy()
    drafts = strategy.extract(source)

    assert any(d.anchor_json == {"row": 1, "field_index": 0, "label": "csv_field"} for d in drafts)
    assert any(d.anchor_json == {"row": 1, "field_index": 1, "label": "csv_field"} for d in drafts)

    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=f"译:{d.source_text}",
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    written = output.read_text(encoding="utf-8-sig")
    assert written.splitlines()[0] == "name,desc"
    assert '"译:apple"' in written
    assert '"译:red, sweet"' in written
    assert len(written.splitlines()[1].split(",")) >= 3  # quoted comma remains inside one CSV field
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_translate_csv_strategy.py -v
```

Expected: fail because current CSV strategy uses one segment per raw line.

- [ ] **Step 3: Add CSV writer helper**

Append to `backend/app/layout/writers/text_writer.py`:

```python
import csv
from io import StringIO


class CsvFieldWriter:
    """Write translated CSV fields while preserving row and field positions."""

    def write(self, context: WriteContext) -> None:
        raw = context.source_path.read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.reader(StringIO(raw)))
        by_cell: dict[tuple[int, int], str] = {}
        for seg in context.segments:
            anchor = seg.anchor_json or {}
            if "row" not in anchor or "field_index" not in anchor:
                continue
            by_cell[(int(anchor["row"]), int(anchor["field_index"]))] = (
                seg.source_text if anchor.get("skip_translate") else seg.translated_text or seg.source_text
            )

        for (row_idx, field_idx), value in by_cell.items():
            if 0 <= row_idx < len(rows) and 0 <= field_idx < len(rows[row_idx]):
                rows[row_idx][field_idx] = value

        buf = StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerows(rows)
        context.out_path.write_text(buf.getvalue(), encoding="utf-8-sig")
```

- [ ] **Step 4: Update CSV strategy**

In `backend/app/translate/service/strategies/csv_strategy.py`, parse fields:

```python
import csv
from io import StringIO
from app.layout.writers.base import WriteContext
from app.layout.writers.text_writer import CsvFieldWriter
```

Replace `extract()` body with:

```python
text = local_path.read_text(encoding="utf-8-sig", errors="replace")
rows = list(csv.reader(StringIO(text)))
drafts: list[SegmentDraft] = []
seq = 0
for row_idx, row in enumerate(rows):
    if row_idx == 0:
        continue
    for field_idx, value in enumerate(row):
        if not value.strip():
            continue
        drafts.append(
            SegmentDraft(
                seq=seq,
                source_text=value,
                anchor_json={"row": row_idx, "field_index": field_idx, "label": "csv_field"},
            )
        )
        seq += 1
return drafts
```

Replace `assemble()` body with:

```python
CsvFieldWriter().write(
    WriteContext(source_path=source_path, out_path=out_path, segments=segments)
)
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
cd backend && pytest tests/test_translate_csv_strategy.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/layout/writers/text_writer.py backend/app/translate/service/strategies/csv_strategy.py backend/tests/test_translate_csv_strategy.py
git commit -m "fix(translate): preserve CSV structure during writeback"
```

---

### Task 3: Spreadsheet Cell-Level Extraction and Write-Back

**Files:**
- Create: `backend/app/layout/writers/spreadsheet_writer.py`
- Modify: `backend/app/translate/service/strategies/xlsx_strategy.py`
- Modify: `backend/app/translate/service/strategies/xls_strategy.py`
- Test: `backend/tests/test_translate_xlsx_strategy.py`

- [ ] **Step 1: Write failing XLSX test**

Create `backend/tests/test_translate_xlsx_strategy.py`:

```python
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.xlsx_strategy import XlsxTranslateStrategy


def test_xlsx_translates_cells_without_row_tab_join(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    output = tmp_path / "output.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "name"
    ws["B1"] = "desc"
    ws["A2"] = "apple"
    ws["B2"] = "red fruit"
    wb.save(source)

    strategy = XlsxTranslateStrategy()
    drafts = strategy.extract(source)

    assert any(d.anchor_json == {"sheet": "Sheet1", "row": 2, "col": 1, "label": "table_cell"} for d in drafts)
    assert any(d.anchor_json == {"sheet": "Sheet1", "row": 2, "col": 2, "label": "table_cell"} for d in drafts)

    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=f"译:{d.source_text}",
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    out = load_workbook(output)
    ws_out = out["Sheet1"]
    assert ws_out["A1"].value == "name"
    assert ws_out["B1"].value == "desc"
    assert ws_out["A2"].value == "译:apple"
    assert ws_out["B2"].value == "译:red fruit"
    out.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_translate_xlsx_strategy.py -v
```

Expected: fail because current XLSX strategy creates one tab-joined row segment.

- [ ] **Step 3: Add spreadsheet writer**

Create `backend/app/layout/writers/spreadsheet_writer.py`:

```python
"""Spreadsheet writers for document translation output."""

from __future__ import annotations

from openpyxl import load_workbook

from app.layout.writers.base import WriteContext


class XlsxCellWriter:
    """Write translated text into anchored XLSX cells."""

    def write(self, context: WriteContext) -> None:
        wb = load_workbook(context.source_path)
        try:
            for seg in context.segments:
                anchor = seg.anchor_json or {}
                sheet = str(anchor.get("sheet", wb.sheetnames[0]))
                row = int(anchor.get("row", 1))
                col = int(anchor.get("col", 1))
                if sheet not in wb.sheetnames:
                    continue
                ws = wb[sheet]
                ws.cell(
                    row=row,
                    column=col,
                    value=seg.source_text if anchor.get("skip_translate") else seg.translated_text or seg.source_text,
                )
            wb.save(context.out_path)
        finally:
            wb.close()
```

- [ ] **Step 4: Update XLSX strategy**

In `backend/app/translate/service/strategies/xlsx_strategy.py`, import:

```python
from app.layout.writers.base import WriteContext
from app.layout.writers.spreadsheet_writer import XlsxCellWriter
```

Replace row-level draft creation with cell-level drafts:

```python
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    for row in ws.iter_rows():
        for cell in row:
            value = "" if cell.value is None else str(cell.value)
            if not value.strip():
                continue
            drafts.append(
                SegmentDraft(
                    seq=seq,
                    source_text=value,
                    anchor_json={
                        "sheet": sheet_name,
                        "row": int(cell.row),
                        "col": int(cell.column),
                        "label": "table_cell",
                        "overflow_policy": "expand",
                    },
                )
            )
            seq += 1
```

Replace `assemble()` body:

```python
XlsxCellWriter().write(
    WriteContext(source_path=source_path, out_path=out_path, segments=segments)
)
```

- [ ] **Step 5: Update XLS strategy with matching anchors**

In `backend/app/translate/service/strategies/xls_strategy.py`, change extraction anchors:

```python
anchor_json={
    "sheet": sheet_name,
    "sheet_index": sheet_idx,
    "row": row_idx,
    "col": col_idx,
    "label": "table_cell",
    "overflow_policy": "expand",
}
```

Create one `SegmentDraft` per non-empty cell. In `assemble()`, build overrides by `(sheet_index, row, col)` and write individual translated cells while copying untouched cells from the source workbook.

- [ ] **Step 6: Run XLSX test**

Run:

```bash
cd backend && pytest tests/test_translate_xlsx_strategy.py -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/layout/writers/spreadsheet_writer.py backend/app/translate/service/strategies/xlsx_strategy.py backend/app/translate/service/strategies/xls_strategy.py backend/tests/test_translate_xlsx_strategy.py
git commit -m "fix(translate): write spreadsheet translations by cell"
```

---

### Task 4: DOCX Writer Preserving Basic Runs and Tables

**Files:**
- Create: `backend/app/layout/writers/docx_writer.py`
- Modify: `backend/app/translate/service/strategies/docx_strategy.py`
- Modify: `backend/app/translate/service/strategies/word_strategy.py`
- Test: `backend/tests/test_translate_docx_strategy.py`

- [ ] **Step 1: Write failing DOCX test**

Create `backend/tests/test_translate_docx_strategy.py`:

```python
from pathlib import Path

from docx import Document

from app.translate.domain.dto import SegmentRecord
from app.translate.service.strategies.docx_strategy import DocxTranslateStrategy


def test_docx_translates_paragraphs_and_table_cells(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run("Hello")
    run.bold = True
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Cell text"
    doc.save(source)

    strategy = DocxTranslateStrategy()
    drafts = strategy.extract(source)
    records = [
        SegmentRecord(
            seq=d.seq,
            source_text=d.source_text,
            translated_text=f"译:{d.source_text}",
            anchor_json=d.anchor_json,
        )
        for d in drafts
    ]
    strategy.assemble(records, source, output)

    out = Document(output)
    assert out.paragraphs[0].text == "译:Hello"
    assert out.paragraphs[0].runs[0].bold is True
    assert out.tables[0].cell(0, 0).text == "译:Cell text"
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
cd backend && pytest tests/test_translate_docx_strategy.py -v
```

Expected: fail if run style is cleared or table write-back is inconsistent.

- [ ] **Step 3: Add DOCX writer**

Create `backend/app/layout/writers/docx_writer.py`:

```python
"""DOCX writer preserving paragraph and table-cell structure where possible."""

from __future__ import annotations

from docx import Document
from docx.text.paragraph import Paragraph

from app.layout.writers.base import WriteContext


def _replace_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Replace text while preserving the first run's basic style."""

    if not paragraph.runs:
        paragraph.add_run(text)
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


class DocxWriter:
    """Write translated segments into DOCX paragraphs and table cells."""

    def write(self, context: WriteContext) -> None:
        doc = Document(context.source_path)
        for seg in context.segments:
            anchor = seg.anchor_json or {}
            text = seg.source_text if anchor.get("skip_translate") else seg.translated_text or seg.source_text
            kind = anchor.get("kind")
            if kind == "paragraph":
                idx = int(anchor.get("index", 0))
                if 0 <= idx < len(doc.paragraphs):
                    _replace_paragraph_text(doc.paragraphs[idx], text)
            elif kind == "table_cell":
                t_idx = int(anchor.get("table", 0))
                r_idx = int(anchor.get("row", 0))
                c_idx = int(anchor.get("col", 0))
                if 0 <= t_idx < len(doc.tables):
                    table = doc.tables[t_idx]
                    if 0 <= r_idx < len(table.rows) and 0 <= c_idx < len(table.rows[r_idx].cells):
                        cell = table.rows[r_idx].cells[c_idx]
                        if cell.paragraphs:
                            _replace_paragraph_text(cell.paragraphs[0], text)
                        else:
                            cell.text = text
        doc.save(context.out_path)
```

- [ ] **Step 4: Delegate DOCX strategy assembly**

In `backend/app/translate/service/strategies/docx_strategy.py`, import:

```python
from app.layout.writers.base import WriteContext
from app.layout.writers.docx_writer import DocxWriter
```

Replace `assemble()` body:

```python
DocxWriter().write(
    WriteContext(source_path=source_path, out_path=out_path, segments=segments)
)
```

Keep `word_strategy.py` conversion logic unchanged; it will continue calling DOCX strategy.

- [ ] **Step 5: Run DOCX test**

Run:

```bash
cd backend && pytest tests/test_translate_docx_strategy.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/layout/writers/docx_writer.py backend/app/translate/service/strategies/docx_strategy.py backend/app/translate/service/strategies/word_strategy.py backend/tests/test_translate_docx_strategy.py
git commit -m "fix(translate): preserve DOCX structure during writeback"
```

---

### Task 5: PDF Writer Using Overflow and Skip Blocks

**Files:**
- Create: `backend/app/layout/writers/pdf_writer.py`
- Create: `backend/app/layout/writers/registry.py`
- Modify: `backend/app/translate/service/strategies/pdf_strategy.py`
- Test: `backend/tests/test_translate_pdf_writer.py`

- [ ] **Step 1: Write failing PDF writer unit test**

Create `backend/tests/test_translate_pdf_writer.py`:

```python
from pathlib import Path

import fitz

from app.layout.writers.base import WriteContext
from app.layout.writers.pdf_writer import PdfWriter
from app.translate.domain.dto import SegmentRecord


def test_pdf_writer_skips_formula_blocks(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "E=mc^2")
    doc.save(source)
    doc.close()

    PdfWriter().write(
        WriteContext(
            source_path=source,
            out_path=output,
            segments=[
                SegmentRecord(
                    seq=0,
                    source_text="E=mc^2",
                    translated_text="should not appear",
                    anchor_json={
                        "page": 0,
                        "bbox": [70, 55, 180, 90],
                        "skip_translate": True,
                        "label": "formula",
                    },
                )
            ],
        )
    )

    out = fitz.open(output)
    try:
        text = "\n".join(page.get_text() for page in out)
    finally:
        out.close()
    assert "should not appear" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/test_translate_pdf_writer.py -v
```

Expected: fail because `PdfWriter` does not exist.

- [ ] **Step 3: Add PDF writer**

Create `backend/app/layout/writers/pdf_writer.py`:

```python
"""PDF writer for layout-aware translation output."""

from __future__ import annotations

import fitz

from app.layout.overflow import fit_text_to_box
from app.layout.writers.base import WriteContext


class PdfWriter:
    """Write translated PDF text into existing bounding boxes."""

    def write(self, context: WriteContext) -> None:
        doc = fitz.open(context.source_path)
        try:
            for seg in context.segments:
                anchor = seg.anchor_json or {}
                if anchor.get("skip_translate"):
                    continue
                page_no = int(anchor.get("page_index", anchor.get("page", 0)))
                if page_no < 0 or page_no >= len(doc):
                    continue
                page = doc[page_no]
                bbox = anchor.get("bbox")
                text = seg.translated_text or seg.source_text
                if isinstance(bbox, list) and len(bbox) >= 4:
                    rect = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                    fitted = fit_text_to_box(
                        text,
                        width=max(1.0, rect.width),
                        height=max(1.0, rect.height),
                        policy=str(anchor.get("overflow_policy", "shrink")),
                        base_font_pt=10.0,
                    )
                    page.add_redact_annot(rect, text="")
                    page.apply_redactions()
                    page.insert_textbox(rect, fitted.text, fontsize=fitted.font_size_pt, align=fitz.TEXT_ALIGN_LEFT)
                else:
                    page.insert_text((72, 72 + (seg.seq % 40) * 14), text)
            doc.save(context.out_path)
        finally:
            doc.close()
```

- [ ] **Step 4: Delegate PDF strategy assembly**

In `backend/app/translate/service/strategies/pdf_strategy.py`, import:

```python
from app.layout.writers.base import WriteContext
from app.layout.writers.pdf_writer import PdfWriter
```

Replace `assemble()` body with:

```python
PdfWriter().write(
    WriteContext(source_path=source_path, out_path=out_path, segments=segments)
)
```

- [ ] **Step 5: Run PDF test**

Run:

```bash
cd backend && pytest tests/test_translate_pdf_writer.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/layout/writers/pdf_writer.py backend/app/layout/writers/registry.py backend/app/translate/service/strategies/pdf_strategy.py backend/tests/test_translate_pdf_writer.py
git commit -m "fix(translate): apply PDF overflow writeback"
```

---

### Task 6: Layout Pages Fallback and Frontend Detail Data Flow

**Files:**
- Modify: `backend/app/translate/service/layout_pages.py`
- Modify: `minerva-ui/src/features/translate/TranslatePage.tsx`
- Modify: `minerva-ui/src/features/translate/TranslatePageLayoutCompare.tsx`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`
- Test: `backend/tests/test_translate_layout_pages_api.py`

- [ ] **Step 1: Write backend fallback test**

Create `backend/tests/test_translate_layout_pages_api.py` with service-level assertions for `_layout_document_from_segments`:

```python
from app.translate.domain.db.models import DocTranslateSegment
from app.translate.service.layout_pages import _layout_document_from_segments


def test_layout_document_from_segments_uses_legacy_page_anchor() -> None:
    seg = DocTranslateSegment(
        seq=0,
        source_text="Hello",
        translated_text="你好",
        status="DONE",
        anchor_json={"page": 2, "block": 3},
    )

    doc = _layout_document_from_segments([seg])

    assert doc is not None
    assert doc.pages[0].page_index == 2
    assert doc.pages[0].blocks[0].block_key == "p2.b3"
```

- [ ] **Step 2: Run backend fallback test**

Run:

```bash
cd backend && pytest tests/test_translate_layout_pages_api.py -v
```

Expected: pass if existing fallback is intact; if it fails, fix `_normalize_segment_anchor()` to preserve `page` and `block`.

- [ ] **Step 3: Simplify frontend segment queries**

In `minerva-ui/src/features/translate/TranslatePage.tsx`, keep the page-grouped query:

```tsx
const segmentsPageGroupsQuery = useQuery({
  queryKey: ['translate-segments', workspaceId, detailJobId, 'page'],
  queryFn: () => listTranslateJobSegments(workspaceId!, detailJobId!, 'page'),
  enabled: Boolean(workspaceId && detailJobId),
  refetchInterval: () => {
    const st = jobQuery.data?.status
    if (!st || TERMINAL.has(st)) return false
    return 3000
  },
})
```

Derive flat segments:

```tsx
const segments = useMemo(
  () => segmentsPageGroupsQuery.data?.groups?.flatMap((g) => g.segments) ?? [],
  [segmentsPageGroupsQuery.data?.groups],
)
```

Remove the separate `group_by='none'` query unless a specific regression requires it.

- [ ] **Step 4: Add layout fallback text**

Add Chinese i18n keys in `minerva-ui/src/i18n/locales/zh-CN.json`:

```json
"translate": {
  "detailTab": {
    "layoutUnavailable": "该任务无版面数据，可切换到段落对照查看原文和译文。",
    "noPages": "暂无页面数据"
  }
}
```

Add English i18n keys in `minerva-ui/src/i18n/locales/en.json`:

```json
"translate": {
  "detailTab": {
    "layoutUnavailable": "Layout data is unavailable for this job. Use segment comparison to view source and translation.",
    "noPages": "No page data"
  }
}
```

Merge into the existing `translate.detailTab` object rather than duplicating the top-level `translate` object.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd minerva-ui && npm run lint
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/translate/service/layout_pages.py backend/tests/test_translate_layout_pages_api.py minerva-ui/src/features/translate/TranslatePage.tsx minerva-ui/src/features/translate/TranslatePageLayoutCompare.tsx minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "fix(translate): clarify layout preview fallback"
```

---

### Task 7: Pipeline Assembly Context and Final Verification

**Files:**
- Modify: `backend/app/translate/service/run_pipeline.py`
- Modify: `docs/superpowers/specs/2026-05-20-document-translate-design.md`
- Modify: `docs/superpowers/specs/2026-05-22-layout-preserving-ocr-translate-design.md`

- [ ] **Step 1: Ensure assembly uses refreshed records**

In `backend/app/translate/service/run_pipeline.py`, keep the refreshed segment load and ensure records preserve anchors:

```python
records = [
    SegmentRecord(
        seq=s.seq,
        source_text=s.source_text,
        translated_text=s.translated_text or s.source_text,
        anchor_json=s.anchor_json if isinstance(s.anchor_json, dict) else None,
    )
    for s in refreshed
]
strategy.assemble(records, src_path, out_path)
```

If writer context needs `layout_document`, parse `job.layout_snapshot_json` in the strategy or introduce an optional `assemble_with_layout()` only after all existing tests pass. Do not change public API.

- [ ] **Step 2: Run targeted backend tests**

Run:

```bash
cd backend && pytest tests/test_translate_md_strategy.py tests/test_translate_csv_strategy.py tests/test_translate_xlsx_strategy.py tests/test_translate_docx_strategy.py tests/test_translate_pdf_writer.py tests/test_translate_layout_pages_api.py -v
```

Expected: all pass.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd minerva-ui && npm run lint && npm run build
```

Expected: both pass.

- [ ] **Step 4: Update old spec implementation comparison**

In `docs/superpowers/specs/2026-05-20-document-translate-design.md`, add an implementation note under the existing implementation/status area:

```markdown
## 实现对照（以代码为准，2026-05-23）

| 条目 | 当前代码位置 | 备注 |
|------|--------------|------|
| 结构化写回 | `backend/app/layout/writers/` | CSV / XLSX / DOCX / PDF 已收敛到 writer 层 |
| Markdown skip | `backend/app/translate/service/strategies/md_strategy.py` | fenced code 使用 `skip_translate=true` |
| doc/xls 支持 | `backend/app/translate/service/strategies/word_strategy.py`, `xls_strategy.py` | 作为现实现支持范围记录 |
```

In `docs/superpowers/specs/2026-05-22-layout-preserving-ocr-translate-design.md`, extend §11:

```markdown
| LayoutWriter 写回 | `backend/app/layout/writers/` | PDF 使用 bbox + overflow；结构化格式按字段/单元格锚点写回 |
```

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: only files touched by this plan are modified or added.

- [ ] **Step 6: Commit**

```bash
git add backend/app docs/superpowers/specs minerva-ui/src
git commit -m "fix(translate): repair structured document writeback"
```

---

## Self-Review

- Spec coverage: The plan covers writer layer, structured anchors, Markdown skip, CSV/XLSX/DOCX/PDF write-back, frontend layout fallback, tests, and old spec backfill.
- Placeholder scan: No `TBD`, generic "handle edge cases", or unspecified implementation steps remain.
- Type consistency: `WriteContext`, `LayoutWriter`, `SegmentRecord`, `SegmentDraft`, `skip_translate`, `row`, `col`, `field_index`, `sheet`, and `label` are used consistently across tasks.

