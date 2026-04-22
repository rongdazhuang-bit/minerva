from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.execution.models import (
    Execution,
    ExecutionEvent,
    ExecutionStatus,
)
from app.domain.rules.ir import ExecutionGraph, build_ir_from_flow
from app.domain.rules.models import RuleVersion


@dataclasses.dataclass
class _StepContext:
    session: AsyncSession
    execution: Execution
    graph: ExecutionGraph
    current_id: str


async def _run_start(ctx: _StepContext) -> str | None:
    targets = ctx.graph.targets.get(ctx.current_id) or []
    if not targets:
        ctx.execution.status = ExecutionStatus.failed.value
        ctx.execution.error_code = "flow.no_edge_from_start"
        ctx.execution.error_detail = "start node has no outgoing edge"
        return None
    return targets[0]


async def _run_end(ctx: _StepContext) -> str | None:
    ctx.execution.status = ExecutionStatus.succeeded.value
    return None


_NODE_RUN: dict[str, Any] = {
    "start": _run_start,
    "end": _run_end,
}


def _as_graph(flow: dict[str, Any]) -> ExecutionGraph:
    return build_ir_from_flow(flow=flow)


async def _log_event(
    session: AsyncSession,
    execution_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    session.add(
        ExecutionEvent(
            execution_id=execution_id,
            event_type=event_type,
            payload=payload,
            resume_nonce=uuid.uuid4(),
        )
    )


async def run_execution_steps(
    session: AsyncSession, *, execution_id: uuid.UUID, max_steps: int | None = None
) -> Execution:
    cap = max_steps if max_steps is not None else settings.execution_max_steps
    execution = await session.get(Execution, execution_id)
    if execution is None:
        msg = f"execution not found: {execution_id}"
        raise ValueError(msg)
    if execution.status in {
        ExecutionStatus.succeeded.value,
        ExecutionStatus.failed.value,
        ExecutionStatus.step_limit.value,
    }:
        return execution

    ver = await session.get(RuleVersion, execution.rule_version_id)
    if ver is None:
        execution.status = ExecutionStatus.failed.value
        execution.error_code = "execution.version_missing"
        await session.flush()
        return execution

    flow = ver.flow_json if isinstance(ver.flow_json, dict) else {}
    graph = _as_graph(flow)

    if execution.current_node_id is None:
        if not graph.entry_ids:
            execution.status = ExecutionStatus.failed.value
            execution.error_code = "flow.no_start"
            await session.flush()
            return execution
        execution.current_node_id = graph.entry_ids[0]
        execution.status = ExecutionStatus.running.value
        await _log_event(
            session, execution.id, "node_enter", {"node": execution.current_node_id}
        )
        await session.flush()

    while True:
        if execution.step_count >= cap:
            execution.status = ExecutionStatus.step_limit.value
            execution.error_code = "execution.step_limit"
            execution.error_detail = f"exceeded {cap} steps"
            await session.flush()
            return execution

        if execution.current_node_id is None:
            return execution

        execution.step_count += 1
        cid = execution.current_node_id
        if cid not in graph.configs:
            execution.status = ExecutionStatus.failed.value
            execution.error_code = "flow.unknown_node_id"
            execution.error_detail = cid
            await session.flush()
            return execution
        ntype = str(graph.configs[cid].get("type", ""))
        run = _NODE_RUN.get(ntype)
        if run is None:
            execution.status = ExecutionStatus.failed.value
            execution.error_code = "node.not_implemented"
            execution.error_detail = ntype
            await session.flush()
            return execution

        ctx = _StepContext(
            session=session, execution=execution, graph=graph, current_id=cid
        )
        nxt: str | None = await run(ctx)

        if execution.status in {
            ExecutionStatus.succeeded.value,
            ExecutionStatus.failed.value,
        }:
            await session.flush()
            return execution

        if ntype == "end":
            await _log_event(session, execution.id, "finished", {"node": cid})
            await session.flush()
            return execution

        if nxt is None:
            await session.flush()
            return execution

        await _log_event(
            session, execution.id, "transition", {"from": cid, "to": nxt}
        )
        execution.current_node_id = nxt
        await _log_event(session, execution.id, "node_enter", {"node": nxt})
        await session.flush()
