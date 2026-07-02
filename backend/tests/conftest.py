"""Shared pytest fixtures for backend unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def db_session() -> AsyncMock:
    """Minimal async session stub until full DB fixtures exist."""

    return AsyncMock()
