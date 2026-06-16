"""Integration and unit tests for PPT source ingestion."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from openpyxl import Workbook

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.skills.ppt.ingest.converters import (
    IngestError,
    build_image_manifest,
    convert_file_to_markdown,
)
from app.agent.skills.ppt.tools import register_tools

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ppt"


@pytest.fixture
def agent_files_root(tmp_path, monkeypatch):
    """Point agent file storage at a temporary directory."""

    monkeypatch.setattr("app.config.resolve_agent_files_root", lambda: tmp_path)
    return tmp_path


def test_convert_file_to_markdown_sample_md() -> None:
    """sample.md converts to non-empty Markdown text."""

    markdown, images = convert_file_to_markdown(FIXTURES / "sample.md")
    assert markdown.strip()
    assert "示例源材料" in markdown
    assert "English section" in markdown
    assert images == []


def test_convert_file_to_markdown_unsupported_format(tmp_path: Path) -> None:
    """Unsupported suffix raises IngestError with code unsupported_format."""

    bad_file = tmp_path / "notes.xyz"
    bad_file.write_text("hello", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        convert_file_to_markdown(bad_file)
    assert exc_info.value.code == "unsupported_format"


def test_convert_file_to_markdown_xlsx(tmp_path: Path) -> None:
    """XLSX workbooks render as Markdown tables."""

    workbook_path = tmp_path / "sheet.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metrics"
    sheet.append(["Name", "Value"])
    sheet.append(["Alpha", "1"])
    workbook.save(workbook_path)
    workbook.close()

    markdown, images = convert_file_to_markdown(workbook_path)
    assert "| Name | Value |" in markdown
    assert "| Alpha | 1 |" in markdown
    assert images == []


def test_build_image_manifest_relative_paths(tmp_path: Path) -> None:
    """Manifest entries use paths relative to the provided base directory."""

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image_path = images_dir / "a.png"
    image_path.write_bytes(b"png")

    manifest = build_image_manifest([image_path], tmp_path)
    assert manifest["count"] == 1
    assert manifest["images"][0]["path"] == "images/a.png"
    assert manifest["images"][0]["filename"] == "a.png"


@pytest.mark.asyncio
async def test_ingest_ppt_source_writes_markdown_and_manifest(agent_files_root) -> None:
    """ingest_ppt_source writes content.md and image_manifest.json in the sandbox."""

    workspace_id = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=workspace_id)
    sample_text = (FIXTURES / "sample.md").read_text(encoding="utf-8")
    await box.write_file_async("sources/sample.md", sample_text)

    ctx = SkillToolContext(workspace_id=workspace_id, chat_model=None)
    tools = register_tools(ctx)
    ingest_tool = next(tool for tool in tools if tool.name == "ingest_ppt_source")

    raw = await ingest_tool.ainvoke(
        {
            "source_path": "sources/sample.md",
            "project_dir": "ppt/default",
        }
    )
    result = json.loads(raw)
    assert result["ok"] is True
    assert result["md_path"] == "ppt/default/sources/content.md"
    assert result["images_dir"] == "ppt/default/sources/images"
    assert result["manifest_path"] == "ppt/default/sources/image_manifest.json"

    md_dest = box.resolve(result["md_path"])
    assert md_dest.is_file()
    assert "示例源材料" in md_dest.read_text(encoding="utf-8")

    manifest_dest = box.resolve(result["manifest_path"])
    manifest = json.loads(manifest_dest.read_text(encoding="utf-8"))
    assert manifest["count"] == 0


@pytest.mark.asyncio
async def test_ingest_ppt_source_unsupported_format(agent_files_root) -> None:
    """Unsupported sandbox files return unsupported_format from the ingest tool."""

    workspace_id = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=workspace_id)
    await box.write_file_async("sources/bad.xyz", "noop")

    ctx = SkillToolContext(workspace_id=workspace_id, chat_model=None)
    ingest_tool = next(tool for tool in register_tools(ctx) if tool.name == "ingest_ppt_source")

    raw = await ingest_tool.ainvoke({"source_path": "sources/bad.xyz"})
    result = json.loads(raw)
    assert result["ok"] is False
    assert result["code"] == "unsupported_format"


@pytest.mark.asyncio
async def test_draft_ppt_outline_includes_source_material(agent_files_root) -> None:
    """draft_ppt_outline appends sandbox Markdown as Source material context."""

    workspace_id = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=workspace_id)
    source_md = (FIXTURES / "sample.md").read_text(encoding="utf-8")
    await box.write_file_async("ppt/default/sources/content.md", source_md)

    outline_doc = {
        "meta": {"title": "封面", "subtitle": "副标题"},
        "slides": [{"pageTitle": "第一页", "body": "来自源材料的大纲"}],
    }
    mock_response = MagicMock()
    mock_response.content = json.dumps(outline_doc, ensure_ascii=False)
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=mock_response)

    ctx = SkillToolContext(workspace_id=workspace_id, chat_model=mock_model)
    draft_tool = next(tool for tool in register_tools(ctx) if tool.name == "draft_ppt_outline")

    raw = await draft_tool.ainvoke(
        {
            "brief": "根据源材料生成演示文稿",
            "source_md_path": "ppt/default/sources/content.md",
        }
    )
    result = json.loads(raw)
    assert result["ok"] is True

    call_args = mock_model.ainvoke.await_args
    messages = call_args.args[0]
    human_content = messages[1].content
    assert "Source material:" in human_content
    assert "示例源材料" in human_content

    outline_path = box.resolve("outlines/draft.json")
    saved = json.loads(outline_path.read_text(encoding="utf-8"))
    assert saved["slides"][0]["pageTitle"] == "第一页"
