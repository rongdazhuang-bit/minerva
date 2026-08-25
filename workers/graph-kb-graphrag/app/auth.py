"""Bearer API key authentication for the GraphRAG graph-kb worker."""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.responses import JSONResponse

_ENV_NAME = "GRAPH_KB_GRAPHRAG_WORKER_API_KEY"
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


def load_expected_api_key(env_name: str) -> str:
    """Load and validate the worker API key from the environment."""

    key = (os.environ.get(env_name) or "").strip()
    if not key:
        print(f"[error] {env_name} is required", file=sys.stderr)
        sys.exit(1)
    return key


EXPECTED_API_KEY: str = load_expected_api_key(_ENV_NAME)


def _keys_match(provided: str, expected: str) -> bool:
    """Compare API keys without raising on length mismatch (Python 3.11+)."""

    if len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Parse ``Authorization: Bearer <token>``; return token or None."""

    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def api_key_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject unauthenticated requests except public probe and OpenAPI paths."""

    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if token is None or not _keys_match(token, EXPECTED_API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)
