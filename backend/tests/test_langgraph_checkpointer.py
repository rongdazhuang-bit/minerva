"""LangGraph checkpoint pool wiring."""

import inspect

from app.agent.infrastructure import langgraph_checkpointer as mod


def test_pool_configures_connection_precheck_and_explicit_open() -> None:
    """Checkpoint pool uses pre-check and explicit ``open(wait=True)`` lifecycle."""

    source = inspect.getsource(mod)
    assert "check=AsyncConnectionPool.check_connection" in source
    assert "open=False" in source
    assert "open(wait=True" in source


def test_pool_sizes_respect_settings() -> None:
    """Pool min/max are derived from settings with max >= min."""

    min_size, max_size = mod._checkpoint_pool_sizes()
    assert min_size >= 1
    assert max_size >= min_size
