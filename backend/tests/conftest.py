"""Pytest fixtures: async engine must not retain connections across event-loop scopes."""

import pytest


@pytest.fixture(autouse=True)
async def dispose_async_engine_after_test() -> None:
    yield
    from app.core.infrastructure.db.session import engine

    await engine.dispose()
