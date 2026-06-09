"""Process-rule segmentation parameter parsing (Dify field names with legacy fallback)."""

from __future__ import annotations

from typing import Any


def _rules_dict(process_rule: dict[str, Any] | None) -> dict[str, Any]:
    """Return nested rules object from a process rule payload."""

    rules = (process_rule or {}).get("rules") or {}
    return rules if isinstance(rules, dict) else {}


def _seg_value(block: dict[str, Any], dify_key: str, legacy_key: str, default: Any) -> Any:
    """Read a segmentation field using Dify name first, then legacy alias."""

    if dify_key in block and block[dify_key] is not None:
        return block[dify_key]
    if legacy_key in block and block[legacy_key] is not None:
        return block[legacy_key]
    return default


def parse_segmentation(process_rule: dict[str, Any] | None) -> tuple[str, int, int]:
    """Read separator/delimiter, max_tokens/max_length, and overlap from segmentation."""

    seg = _rules_dict(process_rule).get("segmentation") or {}
    if not isinstance(seg, dict):
        seg = {}
    delimiter = str(_seg_value(seg, "separator", "delimiter", "\\n\\n"))
    max_length = int(_seg_value(seg, "max_tokens", "max_length", 1024))
    overlap = int(seg.get("chunk_overlap") or 50)
    return delimiter, max_length, overlap


def parse_parent_mode_type(process_rule: dict[str, Any] | None) -> str:
    """Read parent chunk strategy: ``paragraph`` or ``full-doc``."""

    rules = _rules_dict(process_rule)
    raw = rules.get("parent_mode")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    legacy = rules.get("parent_mode_type")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    if isinstance(raw, dict):
        mode = raw.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return "paragraph"


def parse_parent_segmentation(process_rule: dict[str, Any] | None) -> tuple[str, int, int]:
    """Read parent chunk separator, length, and overlap for hierarchical mode."""

    rules = _rules_dict(process_rule)
    parent_mode = parse_parent_mode_type(process_rule)
    parent = rules.get("parent_mode")
    if parent_mode == "full-doc":
        return "\\n\\n", 10_000, 0
    if isinstance(parent, dict):
        block = parent
    else:
        block = rules.get("segmentation") or {}
    if not isinstance(block, dict):
        block = {}
    delimiter = str(_seg_value(block, "separator", "delimiter", "\\n\\n"))
    max_length = int(_seg_value(block, "max_tokens", "max_length", 1024))
    overlap = int(block.get("chunk_overlap") or 100)
    return delimiter, max_length, overlap


def parse_subchunk_segmentation(process_rule: dict[str, Any] | None) -> tuple[str, int, int]:
    """Read child chunk separator, length, and overlap for hierarchical mode."""

    rules = _rules_dict(process_rule)
    sub = rules.get("subchunk_segmentation") or rules.get("segmentation") or {}
    if not isinstance(sub, dict):
        sub = {}
    delimiter = str(_seg_value(sub, "separator", "delimiter", "\\n"))
    max_length = int(_seg_value(sub, "max_tokens", "max_length", 512))
    overlap = int(sub.get("chunk_overlap") or 50)
    return delimiter, max_length, overlap
