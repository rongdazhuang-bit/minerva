"""Memory profile and mem0 management API (mem0 backend only)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.api.v2.schemas import (
    AgentMem0MemoryItemOut,
    AgentMem0MemoryListOut,
    AgentMemoryProfileCreateIn,
    AgentMemoryProfileOut,
    AgentMemoryProfilePatchIn,
)
from app.agent.memory.mem0.client import get_mem0_memory, mem0_entity_filters
from app.agent.memory.profile import repository as profile_repo
from app.config import settings
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError

router = APIRouter(prefix="/memory", tags=["agent-memory"])


def _require_mem0_backend() -> None:
    """Reject when SQL memory backend is active."""

    if settings.agent_memory_backend != "mem0":
        raise AppError(
            "agent.memory_backend_disabled",
            "Memory management API requires AGENT_MEMORY_BACKEND=mem0",
            status_code=404,
        )


def _profile_out(row) -> AgentMemoryProfileOut:
    """Map ORM row to API schema."""

    return AgentMemoryProfileOut(
        id=row.id,
        workspace_id=row.workspace_id,
        session_id=row.session_id,
        profile_text=row.profile_text,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


@router.get("/profiles", response_model=list[AgentMemoryProfileOut])
async def list_memory_profiles(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    _user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> list[AgentMemoryProfileOut]:
    """List persistent profiles for the workspace."""

    _require_mem0_backend()
    rows = await profile_repo.list_profiles(
        db, workspace_id=workspace_id, session_id=session_id
    )
    return [_profile_out(r) for r in rows]


@router.post("/profiles", response_model=AgentMemoryProfileOut, status_code=201)
async def create_memory_profile(
    workspace_id: uuid.UUID,
    body: AgentMemoryProfileCreateIn,
    user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentMemoryProfileOut:
    """Upsert workspace or session profile."""

    _require_mem0_backend()
    row = await profile_repo.upsert_profile(
        db,
        workspace_id=workspace_id,
        session_id=body.session_id,
        profile_text=body.profile_text,
        updated_by=user.id,
    )
    await db.commit()
    return _profile_out(row)


@router.patch("/profiles/{profile_id}", response_model=AgentMemoryProfileOut)
async def patch_memory_profile(
    workspace_id: uuid.UUID,
    profile_id: uuid.UUID,
    body: AgentMemoryProfilePatchIn,
    user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentMemoryProfileOut:
    """Update profile text."""

    _require_mem0_backend()
    row = await profile_repo.get_profile_by_id(
        db, profile_id=profile_id, workspace_id=workspace_id
    )
    if row is None:
        raise AppError("agent.memory_profile_not_found", "Profile not found", 404)
    row.profile_text = body.profile_text
    row.updated_by = user.id
    await db.flush()
    await db.commit()
    return _profile_out(row)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_memory_profile(
    workspace_id: uuid.UUID,
    profile_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one profile row."""

    _require_mem0_backend()
    ok = await profile_repo.delete_profile(
        db, profile_id=profile_id, workspace_id=workspace_id
    )
    if not ok:
        raise AppError("agent.memory_profile_not_found", "Profile not found", 404)
    await db.commit()


@router.get("/memories", response_model=AgentMem0MemoryListOut)
async def list_mem0_memories(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
) -> AgentMem0MemoryListOut:
    """List mem0 memories for a session."""

    _require_mem0_backend()

    def _get_all() -> dict:
        memory = get_mem0_memory()
        return memory.get_all(
            filters=mem0_entity_filters(
                workspace_id=workspace_id,
                session_id=session_id,
            ),
            top_k=limit,
        )

    raw = await asyncio.to_thread(_get_all)
    results = raw.get("results") if isinstance(raw, dict) else raw
    if results is None:
        results = []
    items: list[AgentMem0MemoryItemOut] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "")
        text = (item.get("memory") or item.get("text") or "").strip()
        if not mid and not text:
            continue
        items.append(
            AgentMem0MemoryItemOut(
                id=mid or text[:32],
                memory=text,
                created_at=item.get("created_at"),
            )
        )
    return AgentMem0MemoryListOut(items=items, total=len(items))


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_mem0_memory(
    workspace_id: uuid.UUID,
    memory_id: str,
    _user: User = Depends(get_current_user),
    _member=Depends(require_workspace_member),
) -> None:
    """Delete one mem0 memory by id."""

    _require_mem0_backend()
    _ = workspace_id

    def _delete() -> None:
        get_mem0_memory().delete(memory_id)

    await asyncio.to_thread(_delete)
