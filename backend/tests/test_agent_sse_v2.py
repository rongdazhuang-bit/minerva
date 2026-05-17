"""Tests for SSE v2 envelope serialization."""

import json

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event


def test_build_sse_event_v2() -> None:
    """SSE lines use v2 envelope with run.started type."""

    line = build_sse_event(
        event_type=AgentSseEventType.run_started,
        run_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
        payload={"status": "running"},
    )
    assert line.startswith(b"data: ")
    body = json.loads(line.removeprefix(b"data: ").strip())
    assert body["v"] == 2
    assert body["type"] == "run.started"
