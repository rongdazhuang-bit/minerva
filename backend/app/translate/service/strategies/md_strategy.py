"""Markdown document translation strategy."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import ClassVar

from app.layout.writers.base import WriteContext
from app.layout.writers.text_writer import OrderedTextWriter
from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.text_segmentation import split_plain_text_into_segments

_FENCE_RE = re.compile(r"^```[\w-]*\s*$")


def _is_fenced_code_marker(line: str) -> bool:
    """Return whether ``line`` opens or closes a Markdown fenced code block."""
    return _FENCE_RE.match(line.strip()) is not None


class MdTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.md`` preserving fenced code blocks as single segments."""

    extensions: ClassVar[frozenset[str]] = frozenset({"md"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
        layout_document=None,
    ) -> list[SegmentDraft]:
        """Extract Markdown blocks and mark fenced code as non-translatable."""
        text = local_path.read_text(encoding="utf-8", errors="replace")
        blocks: list[tuple[str, bool]] = []
        buf: list[str] = []
        in_fence = False
        for line in text.splitlines(keepends=True):
            if _is_fenced_code_marker(line):
                if in_fence:
                    buf.append(line)
                    blocks.append(("".join(buf), True))
                    buf = []
                    in_fence = False
                else:
                    if buf:
                        blocks.extend(
                            (segment, False)
                            for segment in split_plain_text_into_segments("".join(buf))
                        )
                        buf = []
                    in_fence = True
                    buf.append(line)
                continue
            buf.append(line)
        if buf:
            if in_fence:
                blocks.append(("".join(buf), True))
            else:
                blocks.extend(
                    (segment, False)
                    for segment in split_plain_text_into_segments("".join(buf))
                )

        drafts: list[SegmentDraft] = []
        seq = 0
        for block, skip_translate in blocks:
            if not block.strip():
                continue
            anchor_json = {"block": seq}
            if skip_translate:
                anchor_json.update(
                    {
                        "label": "code",
                        "skip_translate": True,
                        "overflow_policy": "skip",
                    }
                )
            drafts.append(SegmentDraft(seq=seq, source_text=block, anchor_json=anchor_json))
            seq += 1
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        """Assemble Markdown output from ordered translated segment records."""
        OrderedTextWriter().write(
            WriteContext(source_path=source_path, out_path=out_path, segments=segments)
        )
