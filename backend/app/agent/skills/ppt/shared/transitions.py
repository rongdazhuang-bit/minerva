"""OOXML slide transition helpers for layout_fill output."""

from __future__ import annotations

from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.slide import Slide

_TRANSITION_TAG = qn("p:transition")


def _remove_transition(sld) -> None:
    """Remove an existing p:transition element from the slide root, if any."""

    for child in list(sld):
        if child.tag == _TRANSITION_TAG:
            sld.remove(child)


def _append_fade_transition(sld) -> None:
    """Append a medium-speed fade transition to the slide root."""

    transition = OxmlElement("p:transition")
    transition.set("spd", "med")
    fade = OxmlElement("p:fade")
    transition.append(fade)
    sld.append(transition)


def apply_slide_transition(slide: Slide, transition: str) -> None:
    """Apply, clear, or preserve slide transition per transition mode."""

    mode = (transition or "fade").strip().lower()
    if mode == "keep":
        return

    sld = slide.element
    _remove_transition(sld)

    if mode == "none":
        return

    if mode == "fade":
        _append_fade_transition(sld)
        return

    raise ValueError(f"unsupported transition mode: {transition!r}")
