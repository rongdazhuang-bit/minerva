"""Short-lived HMAC-signed download tokens for local file redirect mode."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings
from app.exceptions import AppError

_ALGO = "HS256"
_DEFAULT_EXPIRES_IN = 600


def create_download_token(
    *,
    workspace_id: uuid.UUID,
    object_key: str,
    expires_in: int = _DEFAULT_EXPIRES_IN,
) -> str:
    """Mint one signed download token for ``workspace_id`` and ``object_key``."""

    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in)
    payload: dict[str, Any] = {
        "wid": str(workspace_id),
        "object_key": object_key,
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def verify_download_token(
    *,
    token: str,
    workspace_id: uuid.UUID,
    object_key: str,
) -> None:
    """Validate token signature, expiry, and payload binding for one download."""

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
    except jwt.PyJWTError as exc:
        raise AppError("local.token_invalid", "Download token is invalid", 401) from exc

    if payload.get("wid") != str(workspace_id):
        raise AppError("local.token_invalid", "Download token workspace mismatch", 401)
    if payload.get("object_key") != object_key:
        raise AppError("local.token_invalid", "Download token object_key mismatch", 401)
