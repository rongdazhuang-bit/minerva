from __future__ import annotations

import uuid

from app.domain.execution.engine import run_execution_steps
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.redis.client import get_redis_client
from app.infrastructure.redis.keys import lock_execution_key

LOCK_TTL = 30


async def handle_execution_tick(_ctx, execution_id: str) -> str:
    """ARQ: run one pass of the step loop (may advance multiple graph nodes)."""
    eid = uuid.UUID(execution_id)
    r = get_redis_client()
    key = lock_execution_key(execution_id)
    token = str(uuid.uuid4())
    ok = await r.set(name=key, value=token, nx=True, ex=LOCK_TTL)
    if not ok:
        return "locked"
    try:
        async with async_session_factory() as session:
            await run_execution_steps(session, execution_id=eid)
            await session.commit()
    finally:
        cur = await r.get(key)
        if cur is not None and cur == token:
            await r.delete(key)
    return "ok"
