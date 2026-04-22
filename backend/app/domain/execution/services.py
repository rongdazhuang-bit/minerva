from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.execution.models import Execution, ExecutionStatus
from app.domain.rules.services import get_rule_in_workspace
from app.exceptions import AppError


async def start_execution(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    input_json: dict | None,
) -> Execution:
    rule = await get_rule_in_workspace(session, rule_id=rule_id, workspace_id=workspace_id)
    if rule.current_published_version_id is None:
        raise AppError("rule.not_published", "Rule has no published version", 400)
    ex = Execution(
        workspace_id=workspace_id,
        rule_id=rule_id,
        rule_version_id=rule.current_published_version_id,
        status=ExecutionStatus.pending.value,
        input_json=input_json or {},
        context_json={},
    )
    session.add(ex)
    await session.flush()
    return ex
