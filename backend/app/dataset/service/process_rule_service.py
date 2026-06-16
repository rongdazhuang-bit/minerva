"""Shared helpers for dataset_process_rule persistence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset.domain.db.models import DatasetProcessRule
from app.dataset.service.chunk_service import serialize_process_rule


async def create_process_rule_row(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    user_id: uuid.UUID,
    rule_payload: dict[str, Any],
) -> uuid.UUID:
    """Insert one DatasetProcessRule row and return its id."""

    row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    return row.id
