"""Tests for RunUsageTracker in-memory aggregation."""

from __future__ import annotations

import uuid

import pytest

from app.agent.infrastructure.usage_tracker import RunUsageTracker


def test_tracker_accumulates_phase_and_builds_snapshot() -> None:
    """Tracker merges planner then subagent into run snapshot."""

    tracker = RunUsageTracker()
    tracker.record_call(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        phase="planner",
    )
    tracker.record_call(
        {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        phase="subagent",
        step_id="s1",
        skill_id="file",
    )
    snap = tracker.build_run_snapshot()
    assert snap["total_tokens"] == 21
    assert snap["by_phase"]["planner"]["total_tokens"] == 15
    assert snap["by_phase"]["subagent"]["total_tokens"] == 6
    assert snap["by_step"]["s1"]["skill_id"] == "file"


@pytest.mark.asyncio
async def test_tracker_record_llm_call_persists_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """record_llm_call writes llm.round node via repository hook."""

    inserted: list[dict] = []

    async def fake_insert(session, **kwargs):
        inserted.append(kwargs)
        row = type("Row", (), {"id": kwargs["node_id"]})()
        return row

    monkeypatch.setattr(
        "app.agent.infrastructure.repository.insert_run_node",
        fake_insert,
    )

    tracker = RunUsageTracker()
    run_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    node_id = await tracker.record_llm_call(
        session=object(),
        run_id=run_id,
        parent_node_id=parent_id,
        sequence_idx=1,
        raw_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        phase="subagent",
        step_id="s1",
        skill_id="general",
    )
    assert node_id is not None
    assert inserted[0]["node_type"] == "llm.round"
    assert inserted[0]["usage_json"]["total_tokens"] == 2
    assert inserted[0]["meta_json"]["phase"] == "subagent"
