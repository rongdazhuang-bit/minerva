"""Tests that the main LangGraph compiles."""

from app.agent.graphs.main import build_main_graph


def test_main_graph_compiles() -> None:
    """Compiled graph exposes expected node names."""

    graph = build_main_graph(checkpointer=None)
    names = set(graph.get_graph().nodes.keys())
    assert "memory.retrieve" in names
    assert "planner" in names
    assert "executor" in names
    assert "synthesizer" in names
