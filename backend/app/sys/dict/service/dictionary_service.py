from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.dict.domain.db.models import SysDict, SysDictItem
from app.sys.dict.infrastructure import repository as repo


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


def _descendants(
    parent_to_children: dict[uuid.UUID, list[uuid.UUID]],
    root: uuid.UUID,
) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    stack = list(parent_to_children.get(root, []))
    while stack:
        cid = stack.pop()
        if cid in out:
            continue
        out.add(cid)
        stack.extend(parent_to_children.get(cid, []))
    return out


def _build_parent_map(items: list[SysDictItem]) -> dict[uuid.UUID, list[uuid.UUID]]:
    m: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for row in items:
        if row.parent_uuid is not None:
            m[row.parent_uuid].append(row.id)
    return m


async def _commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            raise AppError(
                "dict.conflict",
                "Duplicate code in this workspace or dictionary",
                409,
            ) from e
        raise


async def list_dicts(session: AsyncSession, *, workspace_id: uuid.UUID) -> list[SysDict]:
    return list(await repo.list_dicts_for_workspace(session, workspace_id=workspace_id))


async def list_dicts_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[SysDict], int]:
    total = await repo.count_dicts_for_workspace(session, workspace_id=workspace_id)
    offset = (page - 1) * page_size
    rows = await repo.list_dicts_for_workspace_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
    )
    return list(rows), total


async def get_dict(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
) -> SysDict:
    row = await repo.get_dict_for_workspace(
        session, workspace_id=workspace_id, dict_id=dict_id
    )
    if row is None:
        raise AppError("dict.not_found", "Dictionary not found", 404)
    return row


async def create_dict(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_code: str,
    dict_name: str | None,
    dict_sort: int | None,
) -> SysDict:
    now = _utc_now()
    row = SysDict(
        workspace_id=workspace_id,
        dict_code=dict_code.strip(),
        dict_name=dict_name.strip() if dict_name else None,
        dict_sort=dict_sort if dict_sort is not None else 0,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def update_dict(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysDict:
    row = await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    for key, value in patch.items():
        setattr(row, key, value)
    row.update_at = _utc_now()
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def delete_dict(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
) -> None:
    row = await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise AppError("dict.delete_failed", str(e), 400) from e


async def list_items(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
) -> list[SysDictItem]:
    await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    return list(await repo.list_items_for_dict(session, dict_uuid=dict_id))


async def list_items_by_dict_code(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_code: str,
) -> list[SysDictItem]:
    """All items for the dictionary with the given `dict_code` in this workspace; empty if missing."""
    d = await repo.get_dict_by_code_for_workspace(
        session, workspace_id=workspace_id, dict_code=dict_code
    )
    if d is None:
        return []
    return list(await repo.list_items_for_dict(session, dict_uuid=d.id))


async def get_item(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    item_id: uuid.UUID,
) -> SysDictItem:
    await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    row = await repo.get_item_in_dict(session, dict_uuid=dict_id, item_id=item_id)
    if row is None:
        raise AppError("dict.item_not_found", "Dictionary item not found", 404)
    return row


async def create_item(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    code: str,
    name: str,
    item_sort: int | None,
    parent_uuid: uuid.UUID | None,
) -> SysDictItem:
    await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    if parent_uuid is not None:
        parent = await repo.get_item_in_dict(
            session, dict_uuid=dict_id, item_id=parent_uuid
        )
        if parent is None:
            raise AppError("dict.item_parent_invalid", "Parent item not found", 400)

    now = _utc_now()
    row = SysDictItem(
        dict_uuid=dict_id,
        parent_uuid=parent_uuid,
        code=code.strip(),
        name=name.strip(),
        item_sort=item_sort if item_sort is not None else 0,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def update_item(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    item_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysDictItem:
    await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    row = await repo.get_item_in_dict(session, dict_uuid=dict_id, item_id=item_id)
    if row is None:
        raise AppError("dict.item_not_found", "Dictionary item not found", 404)

    if "parent_uuid" in patch:
        new_parent = patch["parent_uuid"]
        if new_parent is not None:
            if new_parent == item_id:
                raise AppError("dict.item_parent_cycle", "Invalid parent", 400)
            parent = await repo.get_item_in_dict(
                session, dict_uuid=dict_id, item_id=new_parent
            )
            if parent is None:
                raise AppError("dict.item_parent_invalid", "Parent item not found", 400)
            all_items = list(
                await repo.list_items_for_dict(session, dict_uuid=dict_id)
            )
            pmap = _build_parent_map(all_items)
            desc = _descendants(pmap, item_id)
            if new_parent in desc:
                raise AppError("dict.item_parent_cycle", "Invalid parent", 400)

    for key, value in patch.items():
        setattr(row, key, value)
    row.update_at = _utc_now()
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def delete_item(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    await get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    row = await repo.get_item_in_dict(session, dict_uuid=dict_id, item_id=item_id)
    if row is None:
        raise AppError("dict.item_not_found", "Dictionary item not found", 404)
    n = await repo.count_direct_children(
        session, dict_uuid=dict_id, parent_id=item_id
    )
    if n > 0:
        raise AppError(
            "dict.item_has_children",
            "Remove child items before deleting this row",
            409,
        )
    await session.delete(row)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise AppError("dict.item_delete_failed", str(e), 400) from e
