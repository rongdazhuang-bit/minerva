"""Build PaddleOCR-VL layout-parsing request bodies from ``SysOcrTool.ocr_config`` plus runtime file data."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.ocr.paddleocr.schemas import LayoutParsingRequest
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from app.sys.tool.ocr.service.ocr_tool_service import normalize_ocr_config_from_db

_LOGGER = logging.getLogger(__name__)

# Keys that must never be taken from persisted config alone (runtime always supplies ``file``).
_FORBIDDEN_CONFIG_KEYS: frozenset[str] = frozenset({"file"})


def _infer_layout_file_type(file_name: str | None, object_key: str) -> int | None:
    """Map filename/object key to Paddle ``fileType`` when inferrable (0=PDF, 1=image)."""

    name = (file_name or "").strip().lower()
    if not name:
        name = (object_key or "").strip().lower()
    if name.endswith(".pdf"):
        return 0
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        return 1
    return None


def _config_has_explicit_file_type(payload: dict[str, Any]) -> bool:
    """Return true when the operator stored a non-null ``fileType`` in ``ocr_config``."""

    for key in ("fileType", "file_type"):
        if key in payload and payload[key] is not None:
            return True
    return False


def ocr_config_to_layout_payload_dict(tool: SysOcrTool) -> dict[str, Any]:
    """Turn ``SysOcrTool.ocr_config`` (dict or JSON string) into a flat request payload fragment.

    Raises:
        ValueError: When ``ocr_config`` is a non-empty string that is not valid JSON object data.
    """

    raw = tool.ocr_config
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw) if raw else {}
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed: Any = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sys_ocr_tool.ocr_config is not valid JSON: {exc}") from exc
        if parsed is None:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
        if isinstance(parsed, list):
            if not parsed:
                return {}
            raise ValueError(
                "sys_ocr_tool.ocr_config JSON array must be empty when no vendor options are stored"
            )
        raise ValueError("sys_ocr_tool.ocr_config JSON must be an object (mapping), not a scalar")
    if isinstance(raw, list):
        if not raw:
            return {}
        raise ValueError(
            "sys_ocr_tool.ocr_config list value must be empty when no vendor options are stored"
        )
    # Fallback: ORM may return already-normalized structures via other drivers.
    normalized = normalize_ocr_config_from_db(raw)
    return dict(normalized) if normalized else {}


def merge_paddle_layout_parsing_payload(
    *,
    file_b64: str,
    file_name: str | None,
    object_key: str,
    tool: SysOcrTool,
) -> dict[str, Any]:
    """Merge persisted vendor options with the worker-fetched file and safe ``fileType`` defaults.

    Precedence:
    1. All keys from ``ocr_config`` (camelCase as stored by the settings UI) except ``file``.
    2. ``file`` is always the Base64 payload built from S3 for this ``ocr_file`` run.
    3. ``fileType`` uses ``ocr_config`` when provided; otherwise it is inferred from filename/key.
    """

    payload = ocr_config_to_layout_payload_dict(tool)
    for key in _FORBIDDEN_CONFIG_KEYS:
        payload.pop(key, None)
    inferred = _infer_layout_file_type(file_name, object_key)
    if not _config_has_explicit_file_type(payload) and inferred is not None:
        payload["fileType"] = inferred
    payload["file"] = file_b64
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "paddle layout-parsing payload keys=%s file_len_b64=%s",
            sorted(payload.keys()),
            len(file_b64),
        )
    return payload


def build_layout_parsing_request_for_tool(
    *,
    file_b64: str,
    file_name: str | None,
    object_key: str,
    tool: SysOcrTool,
) -> LayoutParsingRequest:
    """Validate merged payload into a ``LayoutParsingRequest`` for :func:`post_layout_parsing`."""

    payload = merge_paddle_layout_parsing_payload(
        file_b64=file_b64,
        file_name=file_name,
        object_key=object_key,
        tool=tool,
    )
    try:
        return LayoutParsingRequest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"ocr_config fields are not valid for Paddle layout-parsing: {exc}") from exc
