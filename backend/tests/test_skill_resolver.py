"""Tests for explicit vs automatic skill resolution."""

from __future__ import annotations

from app.agent.infrastructure import skill_resolver

INDEX_IDS = ["example_echo", "system_datetime"]


def test_explicit_mode_only_requested() -> None:
    """Explicit skill_ids restrict to the requested pack only."""

    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点",
        requested_skill_ids=["example_echo"],
        index_skill_ids=INDEX_IDS,
    )
    assert out == ["example_echo"]


def test_explicit_ignores_auto_keywords() -> None:
    """Explicit selection does not auto-add other skills."""

    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点",
        requested_skill_ids=["example_echo"],
        index_skill_ids=INDEX_IDS,
    )
    assert "system_datetime" not in out


def test_auto_matches_system_datetime() -> None:
    """Time-related message auto-selects system_datetime."""

    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点？",
        requested_skill_ids=[],
        index_skill_ids=INDEX_IDS,
    )
    assert out == ["system_datetime"]


def test_auto_empty_for_unrelated() -> None:
    """Unrelated message yields no skills."""

    out = skill_resolver.resolve_effective_skill_ids(
        user_message="你好",
        requested_skill_ids=[],
        index_skill_ids=INDEX_IDS,
    )
    assert out == []
