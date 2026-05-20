"""Keyset cursor encoding for document translation job lists."""

from datetime import UTC, datetime
import uuid

from app.translate.infrastructure.repository import (
    decode_doc_translate_job_cursor,
    encode_doc_translate_job_cursor,
)


def test_job_cursor_roundtrip() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    jid = uuid.uuid4()
    raw = encode_doc_translate_job_cursor(ts, jid)
    got_ts, got_id = decode_doc_translate_job_cursor(raw)
    assert got_id == jid
    assert got_ts == ts
