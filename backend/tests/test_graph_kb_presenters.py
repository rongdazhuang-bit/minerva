"""Tests for GraphKB API presenters (member_user_ids on list responses)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.graph_kb.api.presenters import graph_kb_out_list


@pytest.mark.asyncio
async def test_graph_kb_out_list_includes_member_user_ids() -> None:
    """List responses must batch-load partial member ids like detail responses."""

    workspace_id = uuid4()
    graph_id = uuid4()
    member_a = uuid4()
    member_b = uuid4()
    row = SimpleNamespace(
        id=graph_id,
        workspace_id=workspace_id,
        name="demo",
        description=None,
        engine="lightrag",
        permission="partial_members",
        indexing_status="empty",
        created_by=uuid4(),
        updated_by=None,
        create_at=datetime.now(UTC),
        update_at=None,
    )
    session = AsyncMock()
    with patch(
        "app.graph_kb.api.presenters.repo.list_members_by_graph_ids",
        new=AsyncMock(return_value={graph_id: {member_b, member_a}}),
    ) as batch_mock:
        items = await graph_kb_out_list(session, workspace_id=workspace_id, rows=[row])

    batch_mock.assert_awaited_once_with(
        session,
        workspace_id=workspace_id,
        graph_ids=[graph_id],
    )
    assert items[0].member_user_ids == sorted([member_a, member_b], key=str)
