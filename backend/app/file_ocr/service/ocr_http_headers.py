"""Build HTTP headers for outbound OCR vendor calls from ``SysOcrTool`` credentials."""

from __future__ import annotations

import base64

from app.sys.tool.ocr.domain.db.models import SysOcrTool


def build_ocr_tool_http_headers(tool: SysOcrTool) -> dict[str, str]:
    """Translate stored auth fields into headers understood by typical HTTP OCR gateways."""

    auth = (tool.auth_type or "").strip().upper()
    if auth in {"", "NONE"}:
        return {}
    if auth == "BASIC":
        user = (tool.user_name or "").strip()
        pwd = (tool.user_passwd or "").strip()
        if not user and not pwd:
            return {}
        token = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    if auth == "API_KEY":
        key = (tool.api_key or "").strip()
        if not key:
            return {}
        return {"Authorization": f"Bearer {key}"}
    return {}
