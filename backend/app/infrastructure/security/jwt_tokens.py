from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings

_ALGO = "HS256"


def create_access_token(
    *, user_id: uuid.UUID, tenant_id: uuid.UUID, workspace_id: uuid.UUID
) -> str:
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
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def create_refresh_token(*, user_id: uuid.UUID, jti: uuid.UUID) -> str:
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
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
