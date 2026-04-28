"""工程 / 专业 / 文档类型三元组：规范化与列表筛选（rule_base、rule_config_prompt 共用）。"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import ColumnElement

T = TypeVar("T")


def normalize_scope_triple(
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> tuple[str | None, str | None, str | None]:
    """strip；空串视为 None。"""

    def _one(s: str | None) -> str | None:
        if s is None:
            return None
        t = s.strip()
        return t if t else None

    return (_one(engineering_code), _one(subject_code), _one(document_type))


def scope_triple_filter_conditions(
    model_class: type[T],
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> list[ColumnElement[bool]]:
    """与规则列表一致：仅对非 None 的维度追加等值条件。"""
    conds: list[ColumnElement[bool]] = [model_class.workspace_id == workspace_id]  # type: ignore[attr-defined]
    if engineering_code is not None:
        conds.append(model_class.engineering_code == engineering_code)  # type: ignore[attr-defined]
    if subject_code is not None:
        conds.append(model_class.subject_code == subject_code)  # type: ignore[attr-defined]
    if document_type is not None:
        conds.append(model_class.document_type == document_type)  # type: ignore[attr-defined]
    return conds


def scope_triple_match_conditions(
    model_class: type[T],
    workspace_id: uuid.UUID,
    engineering_code: str | None,
    subject_code: str | None,
    document_type: str | None,
) -> list[ColumnElement[bool]]:
    """精确匹配三元组（含 NULL）。"""
    return [
        model_class.workspace_id == workspace_id,  # type: ignore[attr-defined]
        _eq_or_null(model_class.engineering_code, engineering_code),  # type: ignore[arg-type]
        _eq_or_null(model_class.subject_code, subject_code),  # type: ignore[arg-type]
        _eq_or_null(model_class.document_type, document_type),  # type: ignore[arg-type]
    ]


def _eq_or_null(col: Any, value: str | None) -> ColumnElement[bool]:
    if value is None:
        return col.is_(None)
    return col == value


def normalize_patch_scope_fields(patch: dict[str, Any]) -> dict[str, Any]:
    """PATCH body 中出现的工程三元组字段逐个 strip；空串 -> None。"""
    out = dict(patch)
    for k in ("engineering_code", "subject_code", "document_type"):
        if k not in out:
            continue
        v = out[k]
        if v is None:
            out[k] = None
        elif isinstance(v, str):
            t = v.strip()
            out[k] = t if t else None
    return out
