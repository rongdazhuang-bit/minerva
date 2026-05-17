"""Tests for synthesizer final-answer shortcuts."""

from app.agent.graphs.nodes.synthesizer import resolve_final_answer_from_subagent_results


def test_single_step_skips_second_llm() -> None:
    """One successful sub-agent output becomes the final answer directly."""

    out = resolve_final_answer_from_subagent_results(
        [{"step_id": "s1", "skill_id": "general", "output": "今天是 2026-05-17。"}],
        user_message="今天是几号",
    )
    assert out == "今天是 2026-05-17。"


def test_multi_step_returns_none() -> None:
    """Multiple step results require synthesizer merge LLM call."""

    out = resolve_final_answer_from_subagent_results(
        [
            {"step_id": "s1", "skill_id": "file", "output": "a"},
            {"step_id": "s2", "skill_id": "general", "output": "b"},
        ],
        user_message="整理并回答",
    )
    assert out is None


def test_empty_output_returns_none() -> None:
    """Blank sub-agent output does not short-circuit."""

    out = resolve_final_answer_from_subagent_results(
        [{"step_id": "s1", "skill_id": "general", "output": "  "}],
        user_message="hi",
    )
    assert out is None
