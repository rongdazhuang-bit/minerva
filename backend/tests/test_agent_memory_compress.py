"""Tests for mem0 memory compression service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.agent.service import memory_compress_service as compress_module


def test_parse_created_at_iso_z() -> None:
    """Parse Z-suffixed ISO timestamps."""

    dt = compress_module._parse_created_at("2024-01-15T10:00:00Z")
    assert dt is not None
    assert dt.year == 2024


def test_compress_session_merges_old_memories() -> None:
    """Old memories are summarized, added, and deleted."""

    cutoff = datetime.now(timezone.utc)
    old_ts = (cutoff - timedelta(days=100)).isoformat().replace("+00:00", "Z")
    workspace_id = uuid.uuid4()
    session_id = uuid.uuid4()

    memory = MagicMock()
    memory.get_all.return_value = {
        "results": [
            {"id": "m1", "memory": "likes pizza", "created_at": old_ts},
            {"id": "m2", "memory": "hates broccoli", "created_at": old_ts},
        ]
    }

    with patch.object(
        compress_module, "mem0_llm_complete", return_value="Prefers pizza."
    ):
        stats = compress_module._compress_session(
            memory,
            workspace_id=workspace_id,
            session_id=session_id,
            cutoff=cutoff,
        )

    assert stats["merged"] == 1
    assert stats["deleted"] == 2
    memory.add.assert_called_once()
    assert memory.delete.call_count == 2


def test_compress_session_skips_few_old_items() -> None:
    """Fewer than two old memories are not merged."""

    cutoff = datetime.now(timezone.utc)
    old_ts = (cutoff - timedelta(days=100)).isoformat().replace("+00:00", "Z")
    memory = MagicMock()
    memory.get_all.return_value = {
        "results": [{"id": "m1", "memory": "only one", "created_at": old_ts}]
    }

    stats = compress_module._compress_session(
        memory,
        workspace_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        cutoff=cutoff,
    )
    assert stats["merged"] == 0
    memory.add.assert_not_called()
