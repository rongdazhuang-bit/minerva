"""Tests for PostgreSQL-safe text sanitization in translate persistence."""

from app.translate.infrastructure.pg_text import sanitize_postgres_json, sanitize_postgres_text


def test_sanitize_removes_null_bytes() -> None:
    """Null bytes must not reach asyncpg TEXT parameters."""

    assert sanitize_postgres_text("a\x00b") == "ab"


def test_sanitize_removes_surrogates() -> None:
    """Lone UTF-16 surrogates are stripped."""

    assert sanitize_postgres_text("a\ud800b") == "ab"


def test_sanitize_none_passthrough() -> None:
    """None stays None for nullable columns."""

    assert sanitize_postgres_text(None) is None


def test_sanitize_json_strips_null_in_layout_snapshot() -> None:
    """JSONB layout snapshots must not contain NUL inside nested strings."""

    raw = {
        "pages": [
            {
                "page_index": 0,
                "blocks": [{"block_key": "p0.b0", "source_text": "a\x00b"}],
            }
        ],
        "layout_source": "native",
    }
    cleaned = sanitize_postgres_json(raw)
    assert cleaned["pages"][0]["blocks"][0]["source_text"] == "ab"
