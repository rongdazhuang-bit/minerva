"""Settings validation for GraphKB worker API keys."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_requires_worker_keys_when_engine_client_is_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP engine client mode must require both worker API keys."""

    monkeypatch.setenv("GRAPH_KB_ENGINE_CLIENT", "http")
    monkeypatch.setenv("GRAPH_KB_LIGHTRAG_WORKER_API_KEY", "")
    monkeypatch.setenv("GRAPH_KB_GRAPHRAG_WORKER_API_KEY", "")
    with pytest.raises(ValidationError) as exc:
        Settings()
    msg = str(exc.value)
    assert "GRAPH_KB_LIGHTRAG_WORKER_API_KEY" in msg or "lightrag" in msg.lower()


def test_settings_skips_worker_key_check_when_engine_client_is_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake engine client must not require worker API keys."""

    monkeypatch.setenv("GRAPH_KB_ENGINE_CLIENT", "fake")
    monkeypatch.delenv("GRAPH_KB_LIGHTRAG_WORKER_API_KEY", raising=False)
    monkeypatch.delenv("GRAPH_KB_GRAPHRAG_WORKER_API_KEY", raising=False)
    settings = Settings()
    assert settings.graph_kb_engine_client == "fake"
