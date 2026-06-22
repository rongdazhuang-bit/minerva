"""Short-lived async DB sessions for agent graph runtime (avoid long transactions)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infrastructure.db.session import async_session_factory

T = TypeVar("T")


class AgentRunDbWriter:
    """Open a dedicated session per write/read batch and commit (or rollback) immediately."""

    @asynccontextmanager
    async def session(self, *, read_only: bool = False) -> AsyncIterator[AsyncSession]:
        """Yield one ``AsyncSession``; writers commit on success, readers always rollback."""

        async with async_session_factory() as session:
            if read_only:
                try:
                    yield session
                finally:
                    await session.rollback()
            else:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    async def run(
        self,
        fn: Callable[[AsyncSession], Awaitable[T]],
        *,
        read_only: bool = False,
    ) -> T:
        """Run ``fn(session)`` inside a short-lived session."""

        async with self.session(read_only=read_only) as session:
            return await fn(session)
