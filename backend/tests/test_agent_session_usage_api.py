"""Tests for agent session usage API schemas."""

from __future__ import annotations

from app.agent.api.v2.schemas import AgentSessionListItemOut, AgentSessionOut


def test_agent_session_out_accepts_usage_dict() -> None:
    """Session response model exposes optional usage JSON."""

    row = AgentSessionOut(
        id="00000000-0000-4000-8000-000000000001",
        workspace_id="00000000-0000-4000-8000-000000000002",
        title="t",
        agent_key=None,
        status="active",
        created_at="2026-05-26T00:00:00+00:00",
        usage={"total_tokens": 42, "by_phase": {"planner": {"total_tokens": 10}}},
    )
    assert row.usage is not None
    assert row.usage["total_tokens"] == 42


def test_agent_session_list_item_out_accepts_usage() -> None:
    """Sidebar list item may carry session usage snapshot."""

    item = AgentSessionListItemOut(
        id="00000000-0000-4000-8000-000000000001",
        title="t",
        preview="p",
        created_at="2026-05-26T00:00:00+00:00",
        updated_at=None,
        usage={"total_tokens": 99},
    )
    assert item.usage["total_tokens"] == 99
