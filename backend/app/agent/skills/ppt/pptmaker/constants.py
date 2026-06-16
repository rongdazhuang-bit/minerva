"""PPT maker module constants."""

from __future__ import annotations

from pathlib import Path

AI_MIN_CONFIDENCE = 0.65

_SKILLS_PPT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = _SKILLS_PPT_ROOT / "assets"
DEFAULT_TEMPLATE_PATH = ASSETS_DIR / "template.pptx"
DEFAULT_LAYOUT_INDEX_PATH = ASSETS_DIR / "layout_index.json"

# Default placeholder hint text baked into template.pptx slide layouts
TEMPLATE_PLACEHOLDER_LITERALS = frozenset(
    {
        "要点标题",
        "要点正文",
        "指标名",
        "说明",
        "封面主标题",
        "封面副标题",
        "本页标题",
    }
)
