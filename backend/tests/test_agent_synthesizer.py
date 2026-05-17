"""Tests for synthesizer final-answer resolution."""

from __future__ import annotations

from app.agent.graphs.nodes.synthesizer import resolve_final_answer_from_subagent_results


def test_resolve_final_answer_single_step_skips_resynth() -> None:
    answer = resolve_final_answer_from_subagent_results(
        [{"step_id": "s1", "capability": "general", "output": "今天是 2026-05-17。"}],
        user_message="今天是几号",
    )
    assert answer == "今天是 2026-05-17。"


def test_resolve_final_answer_multi_step_returns_none() -> None:
    assert (
        resolve_final_answer_from_subagent_results(
            [
                {"step_id": "s1", "capability": "file", "output": "a"},
                {"step_id": "s2", "capability": "general", "output": "b"},
            ],
            user_message="汇总",
        )
        is None
    )


def test_resolve_final_answer_empty_output_returns_none() -> None:
    assert (
        resolve_final_answer_from_subagent_results(
            [{"step_id": "s1", "capability": "general", "output": "  "}],
            user_message="hi",
        )
        is None
    )
