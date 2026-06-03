"""Tests for mem0 embedder config resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.memory.mem0.embedder_config import (
    build_embedder_config,
    normalize_openai_embedder_base_url,
    resolve_mem0_embedder_api_base,
    resolve_working_embedder_credentials,
)


@pytest.fixture(autouse=True)
def _clear_embedder_cache() -> None:
    """Reset module-level embedder resolution between tests."""

    import app.agent.memory.mem0.embedder_config as embedder_config

    embedder_config._resolved_embedder = None
    yield
    embedder_config._resolved_embedder = None


def test_normalize_openai_embedder_base_url_appends_v1() -> None:
    """Bare host URLs gain /v1 for OpenAI-compatible embedding clients."""

    assert normalize_openai_embedder_base_url("http://127.0.0.1:8001") == "http://127.0.0.1:8001/v1"
    assert normalize_openai_embedder_base_url("http://127.0.0.1:8001/v1/") == "http://127.0.0.1:8001/v1"


def test_direct_base_url_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEM0_EMBEDDER_DIRECT_BASE_URL overrides MEM0_EMBEDDER_BASE_URL."""

    monkeypatch.setenv("MEM0_EMBEDDER_DIRECT_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("MEM0_EMBEDDER_BASE_URL", "http://litellm:4000/v1")
    import app.config as config_module
    from app.config import Settings

    config_module.settings = Settings()
    assert resolve_mem0_embedder_api_base() == "http://127.0.0.1:8001/v1"
    with patch(
        "app.agent.memory.mem0.embedder_config.probe_embedder_endpoint",
        return_value=True,
    ):
        cfg = build_embedder_config()
    assert cfg["openai_base_url"] == "http://127.0.0.1:8001/v1"


def test_ollama_provider_uses_ollama_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama embedder maps base URL to ollama_base_url without /v1 suffix."""

    monkeypatch.setenv("MEM0_EMBEDDER_PROVIDER", "ollama")
    monkeypatch.setenv("MEM0_EMBEDDER_BASE_URL", "http://127.0.0.1:11434/v1")
    import app.config as config_module
    from app.config import Settings

    config_module.settings = Settings()
    with patch(
        "app.agent.memory.mem0.embedder_config.probe_embedder_endpoint",
        return_value=True,
    ):
        cfg = build_embedder_config()
    assert cfg["ollama_base_url"] == "http://127.0.0.1:11434"


def test_embedder_falls_back_to_llm_base_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unreachable MEM0_EMBEDDER_BASE_URL falls back to MEM0_LLM_BASE_URL."""

    monkeypatch.setenv("MEM0_EMBEDDER_BASE_URL", "http://dead-host:9999")
    monkeypatch.setenv("MEM0_EMBEDDER_API_KEY", "gpustack-key")
    monkeypatch.setenv("MEM0_LLM_BASE_URL", "http://litellm:4000/v1")
    monkeypatch.setenv("MEM0_LLM_API_KEY", "sk-test")
    import app.config as config_module
    from app.config import Settings

    config_module.settings = Settings()

    def _probe(*, base_url: str, api_key: str, model: str) -> bool:
        return base_url == "http://litellm:4000/v1"

    with patch("app.agent.memory.mem0.embedder_config.probe_embedder_endpoint", side_effect=_probe):
        base, key, used_fallback = resolve_working_embedder_credentials()

    assert used_fallback is True
    assert base == "http://litellm:4000/v1"
    assert key == "sk-test"


def test_embedder_defaults_to_llm_when_base_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty embedder URL uses MEM0_LLM_BASE_URL without probing configured host."""

    monkeypatch.setenv("MEM0_EMBEDDER_BASE_URL", "")
    monkeypatch.setenv("MEM0_EMBEDDER_DIRECT_BASE_URL", "")
    monkeypatch.setenv("MEM0_LLM_BASE_URL", "http://litellm:4000/v1")
    monkeypatch.setenv("MEM0_LLM_API_KEY", "sk-test")
    import app.config as config_module
    from app.config import Settings

    config_module.settings = Settings()
    base, key, used_fallback = resolve_working_embedder_credentials()
    assert base == "http://litellm:4000/v1"
    assert key == "sk-test"
    assert used_fallback is True
