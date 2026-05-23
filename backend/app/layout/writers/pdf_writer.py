"""PDF writer for layout-aware translation output."""

from __future__ import annotations

import fitz

from app.layout.overflow import fit_text_to_box
from app.layout.writers.base import WriteContext


class PdfWriter:
    """Write translated PDF text into existing bounding boxes."""

    def write(self, context: WriteContext) -> None:
        """Create a translated PDF by redacting and refilling anchored text boxes."""

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
                    page.insert_textbox(
                        rect,
                        fitted.text,
                        fontsize=fitted.font_size_pt,
                        align=fitz.TEXT_ALIGN_LEFT,
                    )
                else:
                    page.insert_text((72, 72 + (seg.seq % 40) * 14), text)
            doc.save(context.out_path)
        finally:
            doc.close()
