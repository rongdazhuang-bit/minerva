"""MIME and extension validation for agent vision image uploads."""

from __future__ import annotations

from pathlib import Path

ALLOWED_VISION_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


def normalize_vision_mime(raw: str | None) -> str | None:
    """Normalize client MIME types; map non-standard ``image/jpg`` to ``image/jpeg``."""

    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if value == "image/jpg":
        return "image/jpeg"
    return value


def allowed_vision_mime_set(config_value: str) -> frozenset[str]:
    """Parse comma-separated MIME config into a normalized set."""

    parts = [normalize_vision_mime(p) for p in config_value.split(",")]
    return frozenset(p for p in parts if p)


def assert_allowed_vision_extension(file_name: str) -> str:
    """Validate file extension and return the lower-case suffix including dot."""

    suffix = Path(file_name or "").suffix.lower()
    if suffix not in ALLOWED_VISION_EXTENSIONS:
        raise ValueError(f"unsupported extension: {suffix or '(none)'}")
    return suffix
