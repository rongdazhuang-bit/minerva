"""Markdown document translation strategy."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import ClassVar

from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.strategies.txt_strategy import TxtTranslateStrategy, _split_blank_line_paragraphs

_FENCE_RE = re.compile(r"^```[\w-]*\s*$")


class MdTranslateStrategy(DocTranslateFormatStrategy):
    """Translate ``.md`` preserving fenced code blocks as single segments."""

    extensions: ClassVar[frozenset[str]] = frozenset({"md"})

    def extract(
        self,
        local_path: Path,
        *,
        ocr_file_id: uuid.UUID | None = None,
        ocr_pages: list[tuple[int, str]] | None = None,
    ) -> list[SegmentDraft]:
        text = local_path.read_text(encoding="utf-8", errors="replace")
        blocks: list[str] = []
        buf: list[str] = []
        in_fence = False
        for line in text.splitlines(keepends=True):
            if _FENCE_RE.match(line.strip()):
                if in_fence:
                    buf.append(line)
                    blocks.append("".join(buf))
                    buf = []
                    in_fence = False
                else:
                    if buf:
                        blocks.extend(_split_blank_line_paragraphs("".join(buf)))
                        buf = []
                    in_fence = True
                    buf.append(line)
                continue
            buf.append(line)
        if buf:
            if in_fence:
                blocks.append("".join(buf))
            else:
                blocks.extend(_split_blank_line_paragraphs("".join(buf)))

        drafts: list[SegmentDraft] = []
        seq = 0
        for block in blocks:
            if not block.strip():
                continue
            drafts.append(SegmentDraft(seq=seq, source_text=block, anchor_json={"block": seq}))
            seq += 1
        return drafts

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None:
        TxtTranslateStrategy().assemble(segments, source_path, out_path)
