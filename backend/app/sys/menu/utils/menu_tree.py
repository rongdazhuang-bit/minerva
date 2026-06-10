"""Build nested menu trees from flat SysMenu rows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.menu.domain.db.models import SysMenu


@dataclass
class _Node:
    """Internal tree node wrapping a menu row."""

    row: SysMenu
    children: list[_Node] = field(default_factory=list)


def _sort_nodes(nodes: list[_Node]) -> None:
    """Sort siblings by order_num then menu_name."""

    nodes.sort(key=lambda n: (n.row.order_num, n.row.menu_name))
    for n in nodes:
        _sort_nodes(n.children)


def _to_out(n: _Node) -> SysMenuNodeOut:
    """Convert internal node to API schema."""

    return SysMenuNodeOut(
        id=n.row.id,
        parent_id=n.row.parent_id,
        menu_name=n.row.menu_name,
        i18n_key=n.row.i18n_key,
        menu_key=n.row.menu_key,
        order_num=n.row.order_num,
        path=n.row.path,
        menu_type=n.row.menu_type,
        perms=n.row.perms,
        icon=n.row.icon,
        visible=n.row.visible,
        status=n.row.status,
        is_external=n.row.is_external,
        remark=n.row.remark,
        create_at=n.row.create_at,
        update_at=n.row.update_at,
        children=[_to_out(c) for c in n.children],
    )


def build_menu_tree(flat: list[SysMenu]) -> list[SysMenuNodeOut]:
    """Assemble nested menu nodes from a flat query result."""

    if not flat:
        return []
    by_id: dict[uuid.UUID, _Node] = {r.id: _Node(r) for r in flat}
    roots: list[_Node] = []
    for r in flat:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            by_id[r.parent_id].children.append(node)
        else:
            roots.append(node)
    _sort_nodes(roots)
    return [_to_out(n) for n in roots]
