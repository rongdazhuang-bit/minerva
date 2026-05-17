"""Tests for memory extraction models."""

from app.agent.domain.memory_extract import MemoryExtract, MemoryFactItem


def test_memory_extract_validates() -> None:
    """MemoryExtract accepts summary and facts."""

    m = MemoryExtract(
        summary="用户偏好 UTC",
        facts=[MemoryFactItem(key="timezone", content="prefers UTC", tags=["preference"])],
    )
    assert m.summary == "用户偏好 UTC"
    assert len(m.facts) == 1
