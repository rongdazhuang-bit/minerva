"""Compile the main Plan-and-Execute LangGraph."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.nodes.executor import executor_node, route_after_executor
from app.agent.graphs.nodes.memory_nodes import memory_retrieve_node
from app.agent.graphs.nodes.planner import planner_node
from app.agent.graphs.nodes.synthesizer import synthesizer_node
from app.agent.graphs.state import AgentGraphState


def build_main_graph(*, checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the main agent graph."""

    graph = StateGraph(AgentGraphState)
    graph.add_node("memory.retrieve", memory_retrieve_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "memory.retrieve")
    graph.add_edge("memory.retrieve", "planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        route_after_executor,
        {"executor": "executor", "synthesizer": "synthesizer"},
    )
    graph.add_edge("synthesizer", END)

    return graph.compile(checkpointer=checkpointer)
