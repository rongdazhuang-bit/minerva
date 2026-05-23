"""Regression tests for Agent ChatModelFactory independence from app.llm strategies."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
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
    }
    values.update(overrides)
    return SimpleNamespace(**values), workspace_id


def test_agent_chat_model_factory_constructs_chat_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent should keep using LangChain ChatOpenAI with SysModel connection data."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            """Store constructor keyword arguments for assertions."""

            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.ChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row()
    model = ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert isinstance(model, FakeChatOpenAI)
    assert captured == {
        "model": "gpt-compatible",
        "base_url": "https://example.com/v1",
        "api_key": "secret",
        "max_tokens": 512,
    }


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
    """Existing root-style Agent endpoints remain compatible during migration."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            """Store constructor keyword arguments for assertions."""

            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.ChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row(endpoint_url="https://example.com/v1/")
    ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert captured["base_url"] == "https://example.com/v1"


def test_agent_chat_model_factory_rejects_missing_api_key() -> None:
    """Agent model rows still require an API key for ChatOpenAI construction."""

    row, workspace_id = _model_row(api_key="")

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_misconfigured"
