"""Tests for MinerU form builder from SysOcrTool.ocr_config."""

from __future__ import annotations

import uuid

import pytest

from app.file_ocr.service.mineru_ocr_request import (
    build_file_parse_form_for_tool,
    resolve_mineru_url_mode,
)
from app.sys.tool.ocr.domain.db.models import SysOcrTool


def _tool(**kwargs: object) -> SysOcrTool:
    """Build a minimal ``SysOcrTool`` row for unit tests."""
    defaults = {
        "workspace_id": uuid.uuid4(),
        "name": "mineru",
        "url": "http://127.0.0.1:8000/file_parse",
        "ocr_type": "MINERU",
        "ocr_config": None,
    }
    defaults.update(kwargs)
    return SysOcrTool(**defaults)  # type: ignore[arg-type]


def test_resolve_mineru_url_mode_file_parse() -> None:
    """URL ending with /file_parse is sync mode."""
    assert resolve_mineru_url_mode("http://127.0.0.1:8000/file_parse") == "sync"


def test_resolve_mineru_url_mode_tasks() -> None:
    """URL ending with /tasks is async placeholder mode."""
    assert resolve_mineru_url_mode("http://127.0.0.1:8000/tasks") == "async"


def test_build_form_defaults_output_dir() -> None:
    """Empty ocr_config still sends default output_dir=./output."""
    form = build_file_parse_form_for_tool(_tool())
    assert form["output_dir"] == "./output"
    assert form["end_page_id"] == "99999"
    assert form["lang_list"] == ["ch"]


def test_build_form_http_client_requires_server_url() -> None:
    """*-http-client backend without server_url raises ValueError."""
    tool = _tool(ocr_config={"backend": "vlm-http-client"})
    with pytest.raises(ValueError, match="server_url"):
        build_file_parse_form_for_tool(tool)
