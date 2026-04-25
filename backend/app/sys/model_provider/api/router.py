from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_workspace_member
from app.domain.identity.models import User

router = APIRouter(
    prefix="/workspaces/{workspace_id}/model-providers",
    tags=["model-providers"],
)


@router.get("/grouped", response_model=list[dict])
async def list_model_providers_grouped(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> list[dict]:
    """Return provider-grouped model rows; Task 1 skeleton returns an empty list."""
    return []
