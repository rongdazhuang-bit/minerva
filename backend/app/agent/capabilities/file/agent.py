"""Build the file ReAct sub-agent graph."""

from __future__ import annotations

import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.capabilities.file.prompt import FILE_SYSTEM_PROMPT
from app.agent.capabilities.file.tools import build_file_tools


def build_file_react_agent(model: BaseChatModel, *, workspace_id: uuid.UUID) -> CompiledStateGraph:
    """Compile a ReAct agent with workspace-scoped file tools."""

    return create_react_agent(
        model,
        tools=build_file_tools(workspace_id),
        prompt=FILE_SYSTEM_PROMPT,
    )
