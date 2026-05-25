"""Tests for memory.persist usage patching."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.domain.memory_extract import MemoryExtract
from app.agent.service import memory_persist_service as svc


@pytest.mark.asyncio
async def test_persist_turn_memory_merges_memory_persist_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After extract LLM, run/session/message usage include memory.persist phase."""

    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    merge_run = AsyncMock()
    merge_session = AsyncMock()
    patch_message = AsyncMock()
    update_node_usage = AsyncMock()
    insert_node = AsyncMock(return_value=MagicMock())

    monkeypatch.setattr(svc.agent_repo, "insert_run_node", insert_node)
    monkeypatch.setattr(svc.agent_repo, "merge_run_usage_json", merge_run)
    monkeypatch.setattr(svc.agent_repo, "merge_session_usage_json", merge_session)
    monkeypatch.setattr(svc.agent_repo, "patch_assistant_message_usage_by_run", patch_message)
    monkeypatch.setattr(svc.agent_repo, "update_run_node_usage", update_node_usage)

    async def fake_extract(*_args, **_kwargs):
        return MemoryExtract(summary="hi", facts=[]), {
            "prompt_tokens": 5,
            "completion_tokens": 2,
            "total_tokens": 7,
        }

    monkeypatch.setattr(svc, "invoke_memory_extract", fake_extract)

    memory_store = MagicMock()
    memory_store.insert_summary = AsyncMock()
    memory_store.upsert_fact = AsyncMock()
    memory_store.touch_session_summary = AsyncMock()

    run_row = MagicMock()
    run_row.usage_json = {
        "total_tokens": 107,
        "by_phase": {"memory.persist": {"total_tokens": 7}},
    }

    session = MagicMock()
    session.get = AsyncMock(return_value=run_row)

    await svc.persist_turn_memory(
        session,
        model=MagicMock(),
        memory_store=memory_store,
        workspace_id=workspace_id,
        session_id=session_id,
        run_id=run_id,
        user_message="q",
        final_answer="a",
    )

    merge_run.assert_awaited_once()
    delta = merge_run.await_args.kwargs["delta"]
    assert delta["by_phase"]["memory.persist"]["total_tokens"] == 7
    parent_node_id = insert_node.await_args_list[0].kwargs["node_id"]
    llm_round_calls = [
        c for c in insert_node.await_args_list if c.kwargs.get("node_type") == "llm.round"
    ]
    assert len(llm_round_calls) == 1
    assert llm_round_calls[0].kwargs["parent_node_id"] == parent_node_id
    update_node_usage.assert_awaited_once()
    assert update_node_usage.await_args.kwargs["node_id"] == parent_node_id
    assert update_node_usage.await_args.kwargs["usage_json"]["total_tokens"] == 7
    merge_session.assert_awaited_once()
    patch_message.assert_awaited_once()
