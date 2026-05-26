"""Tests for memory.persist session usage merge (no double-counting)."""

from __future__ import annotations

from app.agent.infrastructure.openai_usage import build_phase_delta, merge_usage_document


def _session_delta(doc: dict) -> dict:
    """Mirror ``merge_session_usage_json``: drop per-step buckets."""

    return {k: v for k, v in doc.items() if k != "by_step"}


def _run_usage_after_main_graph() -> dict:
    """Example run totals after graph finalize (before memory.persist)."""

    return {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
        "by_phase": {
            "planner": {"prompt_tokens": 800, "completion_tokens": 120, "total_tokens": 920},
            "synthesizer": {"prompt_tokens": 200, "completion_tokens": 380, "total_tokens": 580},
        },
    }


def _memory_persist_usage() -> dict:
    return {
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 70,
    }


def test_memory_persist_session_merge_adds_only_memory_delta() -> None:
    """Session should gain memory.persist tokens once, not re-merge the whole run."""

    session_after_finalize = _session_delta(_run_usage_after_main_graph())
    memory_delta = build_phase_delta("memory.persist", _memory_persist_usage())

    session_after_memory = merge_usage_document(session_after_finalize, _session_delta(memory_delta))

    assert session_after_memory["total_tokens"] == 1570
    assert session_after_memory["by_phase"]["memory.persist"]["total_tokens"] == 70
    assert session_after_memory["by_phase"]["planner"]["total_tokens"] == 920


def test_memory_persist_full_run_merge_would_double_count() -> None:
    """Regression guard: merging full run snapshot into session inflates totals."""

    session_after_finalize = _session_delta(_run_usage_after_main_graph())
    memory_delta = build_phase_delta("memory.persist", _memory_persist_usage())
    run_after_memory = merge_usage_document(_run_usage_after_main_graph(), memory_delta)

    session_wrong = merge_usage_document(session_after_finalize, _session_delta(run_after_memory))

    assert session_wrong["total_tokens"] == 3070
    assert session_wrong["total_tokens"] != 1570
