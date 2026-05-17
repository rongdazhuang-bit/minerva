"""Build the general ReAct sub-agent graph (no tools)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.capabilities.general.prompt import GENERAL_SYSTEM_PROMPT
def build_general_react_agent(model: BaseChatModel) -> CompiledStateGraph:
    """Compile a general-purpose agent without tools."""

    return create_react_agent(
        model,
        tools=[],
        prompt=GENERAL_SYSTEM_PROMPT,
    )
