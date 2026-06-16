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
