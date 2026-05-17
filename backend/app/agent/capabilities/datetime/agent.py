"""Build the datetime ReAct sub-agent graph."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.capabilities.datetime.prompt import DATETIME_SYSTEM_PROMPT
from app.agent.capabilities.datetime.tools import get_system_datetime
def build_datetime_react_agent(model: BaseChatModel) -> CompiledStateGraph:
    """Compile a ReAct agent with datetime tools."""

    return create_react_agent(
        model,
        tools=[get_system_datetime],
        prompt=DATETIME_SYSTEM_PROMPT,
    )
