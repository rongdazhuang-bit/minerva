from __future__ import annotations

import dataclasses
import uuid
from typing import Any


@dataclasses.dataclass
class ExecutionGraph:
    """Minimal IR: adjacency and node config by id (Task 11–16 skeleton)."""

    node_ids: set[str]
    entry_ids: list[str]
    targets: dict[str, list[str]]  # source node id -> target node ids
    configs: dict[str, dict[str, Any]]


def build_ir_from_flow(*, flow: dict[str, Any]) -> ExecutionGraph:
    from app.domain.rules.flow_validate import parse_flow

    doc = parse_flow(flow)
    targets: dict[str, list[str]] = {n.id: [] for n in doc.nodes}
    cfgs: dict[str, dict[str, Any]] = {n.id: {"type": n.type, **(n.data or {})} for n in doc.nodes}
    for e in doc.edges:
        if e.source in targets:
            targets[e.source].append(e.target)
    entry = [n.id for n in doc.nodes if n.type == "start"]
    return ExecutionGraph(
        node_ids=set(n.id for n in doc.nodes),
        entry_ids=entry,
        targets=targets,
        configs=cfgs,
    )


def new_execution_id() -> uuid.UUID:
    return uuid.uuid4()
