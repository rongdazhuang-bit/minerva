"""Idempotent sys_menu seed for empty databases (dev bootstrap)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infrastructure.db.bootstrap import _dev_like_env, _is_db_unavailable
from app.core.infrastructure.db.session import async_session_factory
from app.core.log import get_logger
from app.sys.menu.domain.db.models import SysMenu

log = get_logger(__name__)

_SEED_SQL = (
    Path(__file__).resolve().parents[4] / "sql" / "seeds" / "sys_menu_seed.sql"
)


async def ensure_sys_menu_seed_if_empty(session: AsyncSession) -> bool:
    """Insert sidebar seed rows when ``sys_menu`` is empty; returns whether seed ran."""

    count = await session.scalar(select(func.count()).select_from(SysMenu))
    if count and count > 0:
        return False
    if not _SEED_SQL.is_file():
        log.warn(
            "sys_menu seed file missing; sidebar will stay empty until SQL is applied",
            event="menu.seed.missing_file",
            path=str(_SEED_SQL),
        )
        return False
    await session.execute(text(_SEED_SQL.read_text(encoding="utf-8")))
    await session.commit()
    log.info("sys_menu seed applied", event="menu.seed.applied")
    return True


async def bootstrap_sys_menu_seed() -> None:
    """On API startup in dev-like env, seed ``sys_menu`` when the table has no rows."""

    if not _dev_like_env():
        return
    try:
        async with async_session_factory() as session:
            await ensure_sys_menu_seed_if_empty(session)
    except Exception as e:
        if _is_db_unavailable(e):
            log.warn(
                "skipped sys_menu seed: database unavailable",
                event="menu.seed.skipped_unavailable",
            )
            return
        log.exception("sys_menu seed failed", event="menu.seed.failed")
        raise
