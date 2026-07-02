"""Shared helpers for user management API routes."""

from __future__ import annotations

from app.core.domain.identity.models import MembershipRole


def parse_membership_role(value: str | None) -> MembershipRole | None:
    """Parse query membership role or return None."""

    if value is None or value.strip() == "":
        return None
    return MembershipRole(value.strip())
