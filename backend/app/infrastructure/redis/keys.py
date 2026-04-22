import os

from app.config import settings


def _prefix() -> str:
    return os.environ.get("REDIS_KEY_PREFIX", settings.redis_key_prefix)


def stream_key(tenant: str, workspace: str) -> str:
    p = _prefix()
    return f"{p}:t:{tenant}:w:{workspace}:stream:events"


def lock_execution_key(execution_id: str) -> str:
    p = _prefix()
    return f"{p}:lock:exec:{execution_id}"
