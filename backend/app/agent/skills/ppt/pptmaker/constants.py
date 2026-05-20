"""PPT maker module constants."""

from __future__ import annotations

from pathlib import Path

AI_MIN_CONFIDENCE = 0.65

_SKILLS_PPT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = _SKILLS_PPT_ROOT / "assets"
DEFAULT_TEMPLATE_PATH = ASSETS_DIR / "template.pptx"
DEFAULT_LAYOUT_INDEX_PATH = ASSETS_DIR / "layout_index.json"
