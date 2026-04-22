from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_workspace_member
from app.dependencies import get_db
from app.domain.rules.flow_validate import parse_flow
from app.domain.rules.ir import build_ir_from_flow
from app.domain.rules.models import Rule, RuleType, RuleVersion, VersionState
from app.domain.rules.services import add_draft_version, publish_rule_version as publish_version_service
from app.exceptions import AppError

router = APIRouter(prefix="/workspaces", tags=["rules"])


class CreateRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern="^(document_review|workflow|policy)$")
    flow_json: dict[str, Any] = Field(default_factory=dict)


class RuleOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    type: str


class AddVersionIn(BaseModel):
    flow_json: dict[str, Any] = Field(default_factory=dict)


class RuleVersionOut(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    version: int
    state: str


@router.post("/{workspace_id}/rules", response_model=RuleOut, status_code=201)
async def create_rule_draft(
    workspace_id: uuid.UUID,
    body: CreateRuleIn,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> RuleOut:
    if body.type not in {t.value for t in RuleType}:
        raise AppError("rule.invalid_type", "Invalid rule type", 400)
    flow: dict[str, Any] = body.flow_json or {}
    if not flow.get("nodes"):
        flow = {
            "schema_version": 1,
            "nodes": [
                {"id": "a", "type": "start", "data": {}},
                {"id": "b", "type": "end", "data": {}},
            ],
            "edges": [{"id": "e1", "source": "a", "target": "b"}],
        }
    try:
        doc = parse_flow(flow)
        build_ir_from_flow(flow=doc.model_dump(mode="json"))
    except ValueError as e:
        text = str(e)
        if "flow.missing_end" in text or "missing end" in text.lower():
            raise AppError("flow.missing_end", "Flow must contain an 'end' node", 400) from e
        raise AppError("flow.unknown_node_type", text, 400) from e
    rule = Rule(
        workspace_id=workspace_id,
        name=body.name,
        type=body.type,
    )
    session.add(rule)
    await session.flush()
    ver = RuleVersion(
        rule_id=rule.id,
        version=1,
        flow_schema_version=1,
        flow_json=doc.model_dump(mode="json"),
        state=VersionState.draft.value,
    )
    session.add(ver)
    await session.commit()
    await session.refresh(rule)
    return RuleOut(
        id=rule.id, workspace_id=rule.workspace_id, name=rule.name, type=rule.type
    )


@router.post(
    "/{workspace_id}/rules/{rule_id}/versions",
    response_model=RuleVersionOut,
    status_code=201,
)
async def add_rule_version(
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: AddVersionIn,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> RuleVersionOut:
    ver = await add_draft_version(
        session,
        rule_id=rule_id,
        workspace_id=workspace_id,
        flow_json=body.flow_json,
    )
    await session.commit()
    return RuleVersionOut(
        id=ver.id, rule_id=ver.rule_id, version=ver.version, state=ver.state
    )


@router.post(
    "/{workspace_id}/rules/{rule_id}/versions/{version_id}/publish",
    response_model=RuleVersionOut,
)
async def publish_rule_version(
    workspace_id: uuid.UUID,
    rule_id: uuid.UUID,
    version_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> RuleVersionOut:
    ver = await publish_version_service(
        session,
        rule_id=rule_id,
        workspace_id=workspace_id,
        version_id=version_id,
    )
    await session.commit()
    await session.refresh(ver)
    return RuleVersionOut(
        id=ver.id, rule_id=ver.rule_id, version=ver.version, state=ver.state
    )
