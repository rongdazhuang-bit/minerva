"""PPT skill tools: draft outline and generate presentation."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.skills.ppt.pptmaker.generate import PptGenerateError, generate_presentation
from app.agent.skills.ppt.pptmaker.layout_select import extract_json_object
from app.agent.skills.ppt.pptmaker.schemas import validate_outline_dict

_OUTLINE_SYSTEM = """你是 PPT 大纲撰写助手。根据用户 brief 生成 JSON 大纲，且只输出 JSON，不要 markdown 围栏。

输出 schema：
{
  "meta": { "title": "封面主标题", "subtitle": "封面副标题" },
  "slides": [
    {
      "pageTitle": "本页标题",
      "items": [{ "title": "要点标题", "body": "要点正文" }],
      "keyNumbers": [{ "number": "19", "label": "指标名", "desc": "说明" }],
      "body": "单段长正文",
      "images": [{ "path": "相对沙箱路径", "caption": "图注" }],
      "hasImage": false
    }
  ]
}

规则：
- meta 可选；有封面需求时填写 title/subtitle。
- 每页只需填一种主要内容形态：items 要点、keyNumbers 指标、body 长正文、或 images 配图。
- images[].path 必须是沙箱内相对路径占位说明（若用户未提供图片，不要编造 path，不要写 images）。
- 指标页用 keyNumbers，数字放 number 字段。
- 不要输出空 slides。"""


async def _sandbox_write_json(
    workspace_id: uuid.UUID,
    path: str,
    data: dict[str, Any],
) -> dict[str, object]:
    """Write JSON to the workspace sandbox."""

    box = AgentFileSandbox(workspace_id=workspace_id)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return await box.write_file_async(path, content)


def register_tools(ctx: SkillToolContext) -> list[Any]:
    """Register PPT maker tools bound to the current workspace and chat model."""

    workspace_id = ctx.workspace_id
    chat_model = ctx.chat_model

    @tool
    async def draft_ppt_outline(
        brief: str,
        slide_count: int | None = None,
        output_path: str = "outlines/draft.json",
    ) -> str:
        """根据自然语言 brief 生成结构化 PPT 大纲 JSON 并写入沙箱。"""

        if not brief.strip():
            return json.dumps(
                {"ok": False, "error": "brief is required", "code": "validation_error"},
                ensure_ascii=False,
            )
        if chat_model is None:
            return json.dumps(
                {"ok": False, "error": "chat model unavailable", "code": "model_unavailable"},
                ensure_ascii=False,
            )

        user_parts = [f"Brief:\n{brief.strip()}"]
        if slide_count is not None and slide_count > 0:
            user_parts.append(f"期望页数约 {slide_count} 页（含封面则 meta+slides）。")

        try:
            response = await chat_model.ainvoke(
                [
                    SystemMessage(content=_OUTLINE_SYSTEM),
                    HumanMessage(content="\n\n".join(user_parts)),
                ]
            )
        except Exception as exc:
            return json.dumps(
                {"ok": False, "error": str(exc), "code": "model_unavailable"},
                ensure_ascii=False,
            )

        text = response.content
        if isinstance(text, list):
            text = "\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in text
            )
        if not isinstance(text, str):
            return json.dumps(
                {"ok": False, "error": "empty model response", "code": "invalid_json"},
                ensure_ascii=False,
            )

        try:
            raw = extract_json_object(text)
        except (json.JSONDecodeError, TypeError) as exc:
            return json.dumps(
                {"ok": False, "error": str(exc), "code": "invalid_json"},
                ensure_ascii=False,
            )

        try:
            doc = validate_outline_dict(raw)
        except Exception as exc:
            return json.dumps(
                {"ok": False, "error": str(exc), "code": "validation_error"},
                ensure_ascii=False,
            )

        outline = doc.model_dump()
        try:
            write_result = await _sandbox_write_json(workspace_id, output_path, outline)
        except AgentFileSandbox.Error as exc:
            return json.dumps(
                {"ok": False, "error": exc.message, "code": "write_failed"},
                ensure_ascii=False,
            )
        if not write_result.get("ok"):
            return json.dumps(write_result, ensure_ascii=False)

        preview = []
        for slide in outline.get("slides", []):
            if not isinstance(slide, dict):
                continue
            preview.append(
                {
                    "pageTitle": slide.get("pageTitle", slide.get("title", "")),
                    "itemCount": len(slide.get("items", []) or []),
                    "hasImages": bool(slide.get("images")) or bool(slide.get("hasImage")),
                }
            )

        return json.dumps(
            {
                "ok": True,
                "path": str(write_result.get("path", output_path)),
                "slides_count": len(outline.get("slides", [])),
                "preview": preview,
            },
            ensure_ascii=False,
        )

    @tool
    async def generate_ppt(
        outline: str = "",
        outline_path: str = "",
        output_path: str = "output/presentation.pptx",
        layout_mode: str = "hybrid",
    ) -> str:
        """从结构化大纲生成 pptx 文件到沙箱。outline 与 outline_path 二选一。"""

        mode = (layout_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "rule"}:
            mode = "hybrid"

        raw_outline: dict[str, Any] | None = None
        if outline_path.strip():
            box = AgentFileSandbox(workspace_id=workspace_id)
            try:
                read_result = await box.read_file_async(outline_path.strip())
            except AgentFileSandbox.Error as exc:
                return json.dumps(
                    {"ok": False, "error": exc.message, "code": "outline_invalid"},
                    ensure_ascii=False,
                )
            if not read_result.get("ok"):
                return json.dumps(read_result, ensure_ascii=False)
            try:
                raw_outline = json.loads(str(read_result.get("content", "")))
            except json.JSONDecodeError as exc:
                return json.dumps(
                    {"ok": False, "error": str(exc), "code": "outline_invalid"},
                    ensure_ascii=False,
                )
        elif outline.strip():
            try:
                raw_outline = json.loads(outline)
            except json.JSONDecodeError as exc:
                return json.dumps(
                    {"ok": False, "error": str(exc), "code": "outline_invalid"},
                    ensure_ascii=False,
                )
        else:
            return json.dumps(
                {
                    "ok": False,
                    "error": "outline or outline_path is required",
                    "code": "outline_invalid",
                },
                ensure_ascii=False,
            )

        if not isinstance(raw_outline, dict):
            return json.dumps(
                {"ok": False, "error": "outline must be a JSON object", "code": "outline_invalid"},
                ensure_ascii=False,
            )

        try:
            validate_outline_dict(raw_outline)
        except Exception as exc:
            return json.dumps(
                {"ok": False, "error": str(exc), "code": "outline_invalid"},
                ensure_ascii=False,
            )

        try:
            result = await generate_presentation(
                raw_outline,
                workspace_id=workspace_id,
                output_path=output_path,
                layout_mode=mode,
                chat_model=chat_model if mode == "hybrid" else None,
            )
        except PptGenerateError as exc:
            return json.dumps(
                {"ok": False, "error": exc.message, "code": exc.code},
                ensure_ascii=False,
            )
        except AgentFileSandbox.Error as exc:
            return json.dumps(
                {"ok": False, "error": exc.message, "code": exc.code},
                ensure_ascii=False,
            )

        return json.dumps(result, ensure_ascii=False)

    return [draft_ppt_outline, generate_ppt]
