"""Build MinerU ``POST /file_parse`` multipart form from ``SysOcrTool.ocr_config``."""

from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from app.ocr.mineru.schemas import FileParseFormOptions
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from app.sys.tool.ocr.service.ocr_tool_service import normalize_ocr_config_from_db

MineruUrlMode = Literal["sync", "async", "invalid"]


def resolve_mineru_url_mode(url: str) -> MineruUrlMode:
    """Infer sync/async from the configured full URL path."""
    path = urlparse(url.strip()).path.rstrip("/").lower()
    if path.endswith("/file_parse"):
        return "sync"
    if path.endswith("/tasks"):
        return "async"
    return "invalid"


def _ocr_config_dict(tool: SysOcrTool) -> dict[str, Any]:
    """Parse ``SysOcrTool.ocr_config`` into a flat dict (mirrors paddle helper)."""
    raw = tool.ocr_config
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        parsed: Any = json.loads(s)
        return dict(parsed) if isinstance(parsed, dict) else {}
    normalized = normalize_ocr_config_from_db(raw)
    return dict(normalized) if normalized else {}


def build_file_parse_form_for_tool(tool: SysOcrTool) -> dict[str, str | list[str]]:
    """Merge persisted MinerU options into multipart form data for ``/file_parse``."""
    payload = _ocr_config_dict(tool)
    try:
        opts = FileParseFormOptions.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"ocr_config fields are not valid for MinerU file_parse: {exc}") from exc
    if opts.backend.endswith("http-client") and not (opts.server_url or "").strip():
        raise ValueError("mineru_missing_server_url")
    return opts.to_form_data()
