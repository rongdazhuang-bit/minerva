"""Tests for mem0ai 2.x filter helpers."""

from __future__ import annotations

import uuid

from app.agent.memory.mem0.client import mem0_entity_filters


def test_mem0_entity_filters_workspace_and_session() -> None:
    """Filters map workspace to user_id and session to run_id."""

    workspace_id = uuid.uuid4()
    session_id = uuid.uuid4()
    assert mem0_entity_filters(
        workspace_id=workspace_id,
        session_id=session_id,
    ) == {
        "user_id": str(workspace_id),
        "run_id": str(session_id),
    }


def test_mem0_entity_filters_workspace_only() -> None:
    """Session id is optional in filters."""

    workspace_id = uuid.uuid4()
    assert mem0_entity_filters(workspace_id=workspace_id) == {
        "user_id": str(workspace_id),
    }
