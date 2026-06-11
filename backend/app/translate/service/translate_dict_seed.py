"""Ensure platform-global ``TRANSLATE_STATUS`` / ``TRANSLATE_SEGMENT_STATUS`` dictionary rows exist."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.dict.domain.db.models import SysDict, SysDictItem
from app.sys.dict.infrastructure import repository as dict_repo
from app.translate.domain.constants import (
    TRANSLATE_SEGMENT_STATUS_DICT_CODE,
    TRANSLATE_SEGMENT_STATUS_DICT_ITEMS,
    TRANSLATE_STATUS_DICT_CODE,
    TRANSLATE_STATUS_DICT_ITEMS,
)


async def _ensure_dict_with_items(
    session: AsyncSession,
    *,
    dict_code: str,
    dict_name: str,
    items: dict[str, tuple[str, int]],
) -> None:
    """Create dictionary category and missing items (idempotent, no commit)."""

    now = datetime.now(UTC)
    row = await dict_repo.get_dict_by_code(session, dict_code=dict_code)
    if row is None:
        row = SysDict(
            dict_code=dict_code,
            dict_name=dict_name,
            dict_sort=0,
            create_at=now,
            update_at=now,
        )
        session.add(row)
        await session.flush()

    existing_codes = {
        item.code
        for item in await dict_repo.list_items_for_dict(session, dict_uuid=row.id)
    }
    for code, (name, item_sort) in items.items():
        if code in existing_codes:
            continue
        session.add(
            SysDictItem(
                dict_uuid=row.id,
                code=code,
                name=name,
                item_sort=item_sort,
                parent_uuid=None,
                create_at=now,
                update_at=now,
            )
        )


async def ensure_translate_status_dicts(session: AsyncSession) -> None:
    """Seed translate job/segment status dictionaries globally if absent."""

    await _ensure_dict_with_items(
        session,
        dict_code=TRANSLATE_STATUS_DICT_CODE,
        dict_name="文档翻译任务状态",
        items=TRANSLATE_STATUS_DICT_ITEMS,
    )
    await _ensure_dict_with_items(
        session,
        dict_code=TRANSLATE_SEGMENT_STATUS_DICT_CODE,
        dict_name="文档翻译段落状态",
        items=TRANSLATE_SEGMENT_STATUS_DICT_ITEMS,
    )
