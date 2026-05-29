"""Tests for LlmService orchestration."""

from __future__ import annotations

import asyncio
import importlib
import uuid

import pytest

from app.llm.domain.models import ChatMessage, TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS, ResolvedModel
from app.llm.service.llm_service import LlmService, build_openai_messages

_LLM_SERVICE_MOD = importlib.import_module("app.llm.service.llm_service")


def test_build_openai_messages_order() -> None:
    """Messages order: system, history, trailing user."""

    msgs = build_openai_messages(
        system_prompt="sys",
        user_prompt="tail",
        messages=[ChatMessage(role="user", content="hist")],
    )
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "hist"}
    assert msgs[2] == {"role": "user", "content": "tail"}


def test_complete_chat_resolves_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """complete_chat resolves model then calls text chat strategy."""

    ws = uuid.uuid4()
    mid = uuid.uuid4()
    resolved = ResolvedModel(
        model_id=mid,
        model_name="m",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="k",
    )
    fake_result = TextChatResult(
        choices=[{"message": {"content": "done"}}],
        raw={},
    )

    async def fake_resolve(session, *, workspace_id, model_id, allowed_tags, excluded_tags=None):  # noqa: ANN001
        assert workspace_id == ws
        assert model_id == mid
        assert allowed_tags == CHAT_MODEL_TAGS
        assert excluded_tags is None
        return resolved

    class _FakeStrategy:
        async def complete(self, r: ResolvedModel, p: TextChatCallParams) -> TextChatResult:
            assert r is resolved
            assert p.messages == [{"role": "user", "content": "hi"}]
            return fake_result

        async def stream(self, r, p):  # noqa: ANN001
            yield {"choices": []}

    monkeypatch.setattr(_LLM_SERVICE_MOD, "resolve_model", fake_resolve)
    monkeypatch.setattr(_LLM_SERVICE_MOD, "get_text_chat_strategy", lambda: _FakeStrategy())

    out = asyncio.run(
        LlmService().complete_chat(
            session=None,  # type: ignore[arg-type]
            workspace_id=ws,
            model_id=mid,
            system_prompt=None,
            user_prompt="hi",
            messages=[],
        )
    )
    assert out.assistant_text() == "done"
