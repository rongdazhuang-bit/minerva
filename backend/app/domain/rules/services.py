from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules.flow_validate import parse_flow
from app.domain.rules.ir import build_ir_from_flow
from app.domain.rules.models import Rule, RuleVersion, VersionState
from app.exceptions import AppError


async def get_rule_in_workspace(
    session: AsyncSession, *, rule_id: uuid.UUID, workspace_id: uuid.UUID
) -> Rule:
    rule = await session.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        raise AppError("rule.not_found", "Rule not found", 404)
    return rule


async def add_draft_version(
    session: AsyncSession,
    *,
    rule_id: uuid.UUID,
    workspace_id: uuid.UUID,
    flow_json: dict,
) -> RuleVersion:
    await get_rule_in_workspace(session, rule_id=rule_id, workspace_id=workspace_id)
    res = await session.execute(
        select(func.coalesce(func.max(RuleVersion.version), 0)).where(
            RuleVersion.rule_id == rule_id
        )
    )
    next_v = int(res.scalar_one()) + 1
    ver = RuleVersion(
        rule_id=rule_id,
        version=next_v,
        flow_schema_version=1,
        flow_json=flow_json,
        state=VersionState.draft.value,
    )
    session.add(ver)
    await session.flush()
    await session.refresh(ver)
    return ver


async def publish_rule_version(
    session: AsyncSession,
    *,
    rule_id: uuid.UUID,
    workspace_id: uuid.UUID,
    version_id: uuid.UUID,
) -> RuleVersion:
    rule = await get_rule_in_workspace(session, rule_id=rule_id, workspace_id=workspace_id)
    res = await session.execute(
        select(RuleVersion).where(
            RuleVersion.id == version_id,
            RuleVersion.rule_id == rule_id,
        )
    )
    ver = res.scalar_one_or_none()
    if ver is None:
        raise AppError("rule.version_not_found", "Version not found", 404)
    if ver.state != VersionState.draft.value:
        raise AppError("rule.invalid_state", "Only draft versions can be published", 400)
    try:
        doc = parse_flow(ver.flow_json)
        build_ir_from_flow(flow=doc.model_dump(mode="json"))
    except ValueError as e:
        text = str(e)
        if "flow.missing_end" in text:
            raise AppError(
                "flow.missing_end", "Flow must contain an 'end' node", 400
            ) from e
        raise AppError("flow.unknown_node_type", text, 400) from e
    ver.state = VersionState.published.value
    rule.current_published_version_id = ver.id
    await session.flush()
    return ver
