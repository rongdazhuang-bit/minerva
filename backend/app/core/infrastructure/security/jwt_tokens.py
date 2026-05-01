"""JWT helpers using HS256 and secrets from ``app.config.settings``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings

_ALGO = "HS256"  # Signing algorithm for access and refresh tokens.


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    workspace_role: str | None = None,
) -> str:
    """Mint a short-lived access JWT including tenant/workspace context."""

    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "wid": str(workspace_id),
        "type": "access",
        "exp": exp,
        "iat": now,
    }
    if workspace_role:
        payload["wrole"] = workspace_role
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def create_refresh_token(*, user_id: uuid.UUID, jti: uuid.UUID) -> str:
    """Mint a long-lived refresh JWT referencing opaque ``jti`` stored server-side."""

    now = datetime.now(UTC)
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": str(jti),
        "type": "refresh",
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT issued by this module or raise ``jwt.PyJWTError``."""

    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
