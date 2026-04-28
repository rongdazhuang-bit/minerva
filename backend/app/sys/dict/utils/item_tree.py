"""Build nested `SysDictItemNodeOut` trees from flat `SysDictItem` rows (parent_uuid links)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.sys.dict.api.schemas import SysDictItemNodeOut
from app.sys.dict.domain.db.models import SysDictItem


@dataclass
class _Node:
    item: SysDictItem
    children: list[_Node] = field(default_factory=list)


def _sort_nodes(nodes: list[_Node]) -> None:
    nodes.sort(key=lambda n: (-(n.item.item_sort or 0), n.item.code))
    for n in nodes:
        _sort_nodes(n.children)


def _to_out(n: _Node) -> SysDictItemNodeOut:
    return SysDictItemNodeOut(
        id=n.item.id,
        dict_uuid=n.item.dict_uuid,
        parent_uuid=n.item.parent_uuid,
        code=n.item.code,
        name=n.item.name,
        item_sort=n.item.item_sort,
        create_at=n.item.create_at,
        update_at=n.item.update_at,
        children=[_to_out(c) for c in n.children],
    )


def build_item_tree(flat: list[SysDictItem]) -> list[SysDictItemNodeOut]:
    if not flat:
        return []
    by_id: dict[uuid.UUID, _Node] = {r.id: _Node(r) for r in flat}
    roots: list[_Node] = []
    for r in flat:
        node = by_id[r.id]
        if r.parent_uuid and r.parent_uuid in by_id:
            by_id[r.parent_uuid].children.append(node)
        else:
            roots.append(node)
    _sort_nodes(roots)
    return [_to_out(n) for n in roots]
