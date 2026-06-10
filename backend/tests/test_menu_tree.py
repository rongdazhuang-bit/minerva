"""Unit tests for sys_menu tree builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.sys.menu.domain.db.models import SysMenu
from app.sys.menu.utils.menu_tree import build_menu_tree


def _row(
    *,
    id: uuid.UUID,
    parent_id: uuid.UUID | None,
    order_num: int,
    name: str,
) -> SysMenu:
    return SysMenu(
        id=id,
        parent_id=parent_id,
        menu_name=name,
        menu_type="C",
        order_num=order_num,
        visible=True,
        status=True,
        is_external=False,
        create_at=datetime.now(UTC),
    )


def test_build_menu_tree_nested_and_sorted() -> None:
    root_id = uuid.uuid4()
    child_a = uuid.uuid4()
    child_b = uuid.uuid4()
    flat = [
        _row(id=child_b, parent_id=root_id, order_num=2, name="B"),
        _row(id=root_id, parent_id=None, order_num=1, name="Root"),
        _row(id=child_a, parent_id=root_id, order_num=1, name="A"),
    ]
    tree = build_menu_tree(flat)
    assert len(tree) == 1
    assert tree[0].menu_name == "Root"
    assert [c.menu_name for c in tree[0].children] == ["A", "B"]
