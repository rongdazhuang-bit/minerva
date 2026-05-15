"""Tests for OpenAI stream chunk accumulation."""

from __future__ import annotations

from app.agent.service.stream_accumulator import LlmStreamAccumulator


def test_accumulator_merges_tool_call_arguments() -> None:
    """Arguments split across chunks are concatenated in order."""

    acc = LlmStreamAccumulator()
    acc.feed(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "echo", "arguments": ""},
                            }
                        ]
                    },
                }
            ]
        }
    )
    acc.feed(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"x":'}}]},
                }
            ]
        }
    )
    acc.feed(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": " 1}"}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    assert acc.finish_reason == "tool_calls"
    tools = acc.build_tool_calls_list()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "echo"
    assert tools[0]["function"]["arguments"] == '{"x": 1}'
    msg = acc.build_assistant_message_dict()
    assert msg["role"] == "assistant"
    assert "tool_calls" in msg
