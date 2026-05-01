import os

import pytest
from sqlalchemy import text

from app.dependencies import get_db
from app.core.infrastructure.db.session import async_session_factory


def _should_skip_db_tests() -> bool:
    if os.environ.get("MINERVA_SKIP_DB_TESTS", "").lower() in ("1", "true", "yes"):
        return True
    return False


pytestmark = pytest.mark.skipif(
    _should_skip_db_tests(),
    reason="Set MINERVA_SKIP_DB_TESTS=1 to skip (e.g. CI without Docker Postgres)",
)


@pytest.mark.asyncio
async def test_session_factory_select_one() -> None:
    async with async_session_factory() as s:
        v = (await s.execute(text("select 1"))).scalar_one()
    assert v == 1


@pytest.mark.asyncio
async def test_get_db_yields_working_session() -> None:
    """FastAPI will iterate `get_db` once per request; same pattern as a single `async for` body."""
    async for session in get_db():
        v = (await session.execute(text("select 1"))).scalar_one()
        assert v == 1
