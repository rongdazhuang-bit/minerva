"""Async SQLAlchemy engine and session factory for FastAPI dependencies."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.infrastructure.db.sql_logging import create_app_async_engine

engine = create_app_async_engine(  # Global async engine (asyncpg); shared across sessions.
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"timeout": 10},
)

async_session_factory = async_sessionmaker(  # Called per-request via ``get_db``.
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
