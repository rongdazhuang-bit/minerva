"""Pytest fixtures: async engine must not retain connections across event-loop scopes."""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def disable_login_captcha_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most API tests predate login CAPTCHA; keep them credential-only."""

    monkeypatch.setattr(settings, "auth_login_captcha_enabled", False)


@pytest.fixture(autouse=True)
async def dispose_async_engine_after_test() -> None:
    yield
    from app.core.infrastructure.db.session import engine

    await engine.dispose()
