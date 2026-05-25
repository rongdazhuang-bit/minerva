"""Tests for OpenAI usage normalization helpers."""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.agent.infrastructure.openai_usage import (
    extract_usage_document,
    extract_usage_from_langchain_output,
    merge_openai_usage,
    merge_usage_document,
    normalize_openai_usage,
)


def test_normalize_openai_usage_from_openai_keys() -> None:
    """OpenAI ``usage`` keys pass through unchanged."""

    assert normalize_openai_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    ) == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


def test_normalize_openai_usage_from_langchain_metadata() -> None:
    """LangChain ``usage_metadata`` maps to OpenAI keys."""

    assert normalize_openai_usage(
        {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12}
    ) == {
        "prompt_tokens": 8,
        "completion_tokens": 4,
        "total_tokens": 12,
    }


def test_normalize_openai_usage_computes_total_when_missing() -> None:
    """Total tokens are derived when only prompt/completion are present."""

    assert normalize_openai_usage({"prompt_tokens": 3, "completion_tokens": 7}) == {
        "prompt_tokens": 3,
        "completion_tokens": 7,
        "total_tokens": 10,
    }


def test_extract_usage_from_ai_message() -> None:
    """Usage is read from ``AIMessage.usage_metadata``."""

    msg = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    )
    assert extract_usage_from_langchain_output(msg) == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


def test_extract_usage_from_response_metadata() -> None:
    """Legacy ``response_metadata.token_usage`` is supported."""

    msg = AIMessage(
        content="hi",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 4,
                "completion_tokens": 6,
                "total_tokens": 10,
            }
        },
    )
    assert extract_usage_from_langchain_output(msg) == {
        "prompt_tokens": 4,
        "completion_tokens": 6,
        "total_tokens": 10,
    }


def test_extract_usage_from_llm_result() -> None:
    """``LLMResult`` generations are scanned for usage."""

    msg = AIMessage(
        content="x",
        usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    )
    result = LLMResult(generations=[[ChatGeneration(message=msg)]])
    assert extract_usage_from_langchain_output(result) == {
        "prompt_tokens": 2,
        "completion_tokens": 1,
        "total_tokens": 3,
    }


def test_merge_openai_usage_sums_counts() -> None:
    """Merged usage aggregates all standard keys."""

    assert merge_openai_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    ) == {
        "prompt_tokens": 13,
        "completion_tokens": 7,
        "total_tokens": 20,
    }


def test_merge_usage_document_merges_by_phase_and_details() -> None:
    """Layered usage documents sum top-level, details, and by_phase buckets."""

    base = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "details": {"cached_tokens": 2},
        "by_phase": {
            "planner": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }
    delta = {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
        "details": {"cached_tokens": 1, "reasoning_tokens": 4},
        "by_phase": {
            "subagent": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "by_step": {
            "s1": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "skill_id": "file",
            },
        },
    }
    merged = merge_usage_document(base, delta)
    assert merged == {
        "prompt_tokens": 13,
        "completion_tokens": 7,
        "total_tokens": 20,
        "details": {"cached_tokens": 3, "reasoning_tokens": 4},
        "by_phase": {
            "planner": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "subagent": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "by_step": {
            "s1": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "skill_id": "file",
            },
        },
    }


def test_extract_usage_document_with_cached_and_reasoning_details() -> None:
    """``extract_usage_document`` keeps optional detail token counts."""

    doc = extract_usage_document(
        {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 8},
            "completion_tokens_details": {"reasoning_tokens": 3},
        }
    )
    assert doc == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "details": {"cached_tokens": 8, "reasoning_tokens": 3},
    }


def test_merge_usage_document_preserves_skill_id_on_step() -> None:
    """by_step merge keeps skill_id from the latest delta when present."""

    merged = merge_usage_document(
        {"by_step": {"s1": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "skill_id": "general"}}},
        {"by_step": {"s1": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3, "skill_id": "file"}}},
    )
    assert merged["by_step"]["s1"]["skill_id"] == "file"
    assert merged["by_step"]["s1"]["total_tokens"] == 5
