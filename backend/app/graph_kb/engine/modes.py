"""Validate unified GraphKB query modes per engine."""

from __future__ import annotations

from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    ENGINE_GRAPHRAG,
    ENGINE_LIGHTRAG,
    QUERY_BASIC,
    QUERY_MODES,
    QUERY_NAIVE,
)


def map_query_mode(engine: str, mode: str) -> str:
    """Validate unified mode; GraphRAG rejects naive; LightRAG rejects basic."""

    if mode not in QUERY_MODES:
        raise AppError("graph_kb.invalid_mode", "不支持的检索模式。", 400)
    if engine == ENGINE_GRAPHRAG and mode == QUERY_NAIVE:
        raise AppError("graph_kb.invalid_mode", "GraphRAG 不支持 naive 模式。", 400)
    if engine == ENGINE_LIGHTRAG and mode == QUERY_BASIC:
        raise AppError("graph_kb.invalid_mode", "LightRAG 不支持 basic 模式。", 400)
    return mode
