"""Tests for planner datetime intent heuristics."""

from app.agent.domain.intent_routing import detect_datetime_intent


def test_detect_datetime_intent_positive() -> None:
    """Common Chinese date/time questions match."""

    assert detect_datetime_intent("今天是几号")
    assert detect_datetime_intent("现在几点了？")
    assert detect_datetime_intent("今天星期几")


def test_detect_datetime_intent_negative() -> None:
    """Unrelated prompts should not match."""

    assert not detect_datetime_intent("你好")
    assert not detect_datetime_intent("帮我总结这段文字")
