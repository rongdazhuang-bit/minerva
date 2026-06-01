"""Regression tests for Agent ChatModelFactory independence from app.llm strategies."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from openai import AsyncOpenAI

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.agent.infrastructure.thinking_config import ThinkingConfig
from app.exceptions import AppError


def _model_row(**overrides):
    """Build the minimal SysModel-like row needed by ChatModelFactory."""

    workspace_id = overrides.pop("workspace_id", uuid.uuid4())
    values = {
        "workspace_id": workspace_id,
        "enabled": True,
        "endpoint_url": "https://example.com/v1/chat/completions",
        "api_key": "secret",
        "model_name": "gpt-compatible",
        "max_tokens_to_sample": 512,
        "tags": ["CHAT"],
    }
    values.update(overrides)
    return SimpleNamespace(**values), workspace_id


def test_agent_chat_model_factory_constructs_chat_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent should use a direct-endpoint AsyncOpenAI client with SysModel connection data."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            """Store constructor keyword arguments for assertions."""

            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.AgentChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row()
    model = ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert isinstance(model, FakeChatOpenAI)
    assert captured["model"] == "gpt-compatible"
    assert captured["api_key"] == "secret"
    assert captured["max_tokens"] == 512
    assert "base_url" not in captured
    root_async_client = captured["root_async_client"]
    assert isinstance(root_async_client, AsyncOpenAI)
    assert captured["async_client"] is root_async_client.chat.completions


def test_agent_chat_model_factory_rejects_wrong_workspace() -> None:
    """Workspace ownership remains validated independently of LLM strategies."""

    row, _workspace_id = _model_row()

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=uuid.uuid4())

    assert exc.value.code == "agent.model_not_found"


def test_agent_chat_model_factory_rejects_missing_endpoint() -> None:
    """Agent model rows still require an OpenAI-compatible endpoint URL."""

    row, workspace_id = _model_row(endpoint_url="")

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_misconfigured"


def test_agent_chat_model_factory_accepts_root_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured endpoint URLs are passed through without stripping path suffixes."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            """Store constructor keyword arguments for assertions."""

            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.AgentChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row(endpoint_url="https://example.com/v1/")
    ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    client = captured["root_async_client"]
    assert isinstance(client, AsyncOpenAI)


def test_agent_chat_model_factory_preserves_direct_endpoint_client() -> None:
    """ChatOpenAI must keep the configured AsyncOpenAI instead of defaulting to OpenAI."""

    row, workspace_id = _model_row()
    model = ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert str(model.root_async_client.base_url).rstrip("/") == "https://example.com"
    assert model.async_client is model.root_async_client.chat.completions


def test_chat_model_factory_injects_extra_body_when_thinking_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When thinking is enabled with non-empty extra_body, AgentChatOpenAI gets extra_body."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            """Store constructor keyword arguments for assertions."""

            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.AgentChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row()
    extra = {"enable_thinking": True, "thinking_budget": 1024}
    thinking = ThinkingConfig(enabled=True, extra_body=extra)
    ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id, thinking=thinking)

    assert captured["extra_body"] == extra
    assert captured["extra_body"] is not thinking.extra_body


def test_agent_chat_model_factory_rejects_missing_chat_tag() -> None:
    """Models without the CHAT tag cannot be used for agent graphs."""

    row, workspace_id = _model_row(tags=["EMBEDDINGS"])

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_tag_not_allowed"


def test_agent_chat_model_factory_accepts_chat_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """CHAT among multiple tags satisfies agent model selection."""

    monkeypatch.setattr(
        "app.agent.infrastructure.chat_model_factory.AgentChatOpenAI",
        lambda **kwargs: object(),
    )
    row, workspace_id = _model_row(tags=["CHAT", "EMBEDDINGS"])
    ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)


def test_agent_chat_model_factory_rejects_text_without_chat_tag() -> None:
    """TEXT alone does not satisfy agent conversation tag requirement."""

    row, workspace_id = _model_row(tags=["TEXT"])

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_tag_not_allowed"


def test_agent_chat_model_factory_rejects_missing_api_key() -> None:
    """Agent model rows still require an API key for ChatOpenAI construction."""

    row, workspace_id = _model_row(api_key="")

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_misconfigured"
