"""Unit tests for hybrid retrieval score merge."""

from __future__ import annotations

from app.dataset.rag.retrieval.retrieval_service import _merge_hybrid


def test_merge_hybrid_combines_vector_and_keyword_scores() -> None:
    """Hybrid merge weights semantic and keyword hits."""

    merged = _merge_hybrid(
        [("node-a", 0.8), ("node-b", 0.2)],
        [("node-b", 1.0), ("node-c", 0.5)],
        vector_weight=0.7,
        keyword_weight=0.3,
        top_k=3,
    )
    scores = dict(merged)
    assert "node-a" in scores
    assert "node-b" in scores
    assert "node-c" in scores
    assert scores["node-a"] == 0.5599999999999999
