"""LangGraph checkpoint pool wiring."""

import inspect

from app.agent.infrastructure import langgraph_checkpointer as mod


def test_pool_configures_connection_precheck() -> None:
    """Checkpoint pool passes psycopg ``check_connection`` (equivalent to pool_pre_ping)."""

    source = inspect.getsource(mod.get_langgraph_checkpointer)
    assert "check=AsyncConnectionPool.check_connection" in source
