"""FastAPI dependency that yields one SQLAlchemy async session per request."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped ``AsyncSession`` from the shared session factory."""

    async with async_session_factory() as session:
        yield session
