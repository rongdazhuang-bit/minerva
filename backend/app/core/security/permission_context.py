"""Resolved authorization snapshot for one authenticated request."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.domain.identity.models import MembershipRole


@dataclass(frozen=True)
class PermissionContext:
    """Effective permissions and ABAC attributes for the current principal."""

    user_id: uuid.UUID
    is_super_admin: bool
    tenant_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    tenant_role: MembershipRole | None
    workspace_role: MembershipRole | None
    is_tenant_admin: bool
    tenant_features: frozenset[str]
    permissions: frozenset[str]
    menu_ids: frozenset[uuid.UUID]
