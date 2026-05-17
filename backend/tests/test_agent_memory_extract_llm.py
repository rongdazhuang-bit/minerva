"""Tests for memory extract parsing and fallbacks."""

import json

from app.agent.domain.memory_extract import MemoryExtract, MemoryFactItem
from app.agent.service.memory_extract_llm import (
    fallback_memory_extract,
    parse_memory_extract_text,
)


def test_parse_memory_extract_json_object() -> None:
    """Valid JSON object parses into MemoryExtract."""

    raw = json.dumps(
        {
            "summary": "用户询问日期",
            "facts": [{"key": "tz", "content": "UTC", "tags": []}],
        },
        ensure_ascii=False,
    )
    out = parse_memory_extract_text(raw)
    assert out is not None
    assert out.summary == "用户询问日期"
    assert len(out.facts) == 1


def test_parse_memory_extract_summary_prefix() -> None:
    """Loose ``summary:`` prefix from non-JSON models is accepted."""

    raw = 'summary: 助手展示了 printf("Hello, World!\\n");'
    out = parse_memory_extract_text(raw)
    assert out is not None
    assert "printf" in out.summary
    assert out.facts == []


def test_parse_memory_extract_json_fence() -> None:
    """Markdown fenced JSON is parsed."""

    raw = '```json\n{"summary":"ok","facts":[]}\n```'
    out = parse_memory_extract_text(raw)
    assert out is not None
    assert out.summary == "ok"


def test_fallback_memory_extract() -> None:
    """Fallback always returns a non-empty summary."""

    out = fallback_memory_extract("今天几号", "今天是 2026 年 5 月 17 日。")
    assert "今天几号" in out.summary
    assert out.facts == []


def test_memory_extract_model_empty_facts() -> None:
    """MemoryExtract validates empty facts list."""

    m = MemoryExtract(summary="x", facts=[])
    assert m.facts == []
    m2 = MemoryExtract(
        summary="y",
        facts=[MemoryFactItem(content="fact", tags=["t"])],
    )
    assert len(m2.facts) == 1
