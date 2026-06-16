"""Tests for agent session delete helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.agent.infrastructure import repository as repo
from app.exceptions import AppError


def test_is_db_lock_timeout_detects_message() -> None:
    """Lock timeout helper matches PostgreSQL timeout text."""

    assert repo._is_db_lock_timeout(Exception("canceling statement due to lock timeout"))


def test_is_db_lock_timeout_ignores_other_errors() -> None:
    """Unrelated DB errors are not treated as lock timeouts."""

    assert not repo._is_db_lock_timeout(Exception("duplicate key value"))


@pytest.mark.asyncio
async def test_delete_agent_session_raises_busy_on_lock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete surfaces 409 when PostgreSQL lock wait times out."""

    session = AsyncMock()
    row = object()
    ws = uuid.uuid4()
    sid = uuid.uuid4()

    async def fake_get_agent_session(
        _session: object, *, workspace_id: uuid.UUID, session_id: uuid.UUID
    ) -> object:
        assert workspace_id == ws
        assert session_id == sid
        return row

    async def fake_set_lock_timeout(_session: object, *, timeout_ms: int) -> None:
        assert timeout_ms == repo.AGENT_SESSION_DELETE_LOCK_TIMEOUT_MS

    async def fake_cancel_running(
        _session: object, *, workspace_id: uuid.UUID, session_id: uuid.UUID
    ) -> int:
        return 1

    async def boom_execute(*_args: object, **_kwargs: object) -> None:
        raise DBAPIError("DELETE", {}, Exception("lock timeout"))

    session.execute = boom_execute

    monkeypatch.setattr(repo, "get_agent_session", fake_get_agent_session)
    monkeypatch.setattr(repo, "_set_local_lock_timeout", fake_set_lock_timeout)
    monkeypatch.setattr(repo, "cancel_running_agent_runs_for_session", fake_cancel_running)

    with pytest.raises(AppError) as exc:
        await repo.delete_agent_session(session, workspace_id=ws, session_id=sid)

    assert exc.value.code == "agent.session_busy"
    assert exc.value.status_code == 409
