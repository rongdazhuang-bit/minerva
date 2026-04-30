"""Executable beat runtime entrypoints for bootstrap, sync-event apply, and reconcile.

Beat integration should call this flow from its process hooks:
1) startup: ``create_beat_runtime_state(session)``
2) each pub/sub message: ``process_sync_message_once(runtime, payload, job_payload=...)``
3) periodic maintenance: ``run_reconcile_cycle_once(runtime, rows, now_epoch_seconds=...)``
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.service.beat_bootstrap import (
    load_enabled_schedule_state,
    run_reconcile_once_if_due,
)
from app.sys.celery.service.beat_sync_service import BeatSyncState, apply_sync_event


@dataclass
class CeleryBeatRuntimeState:
    """Runtime state container held by the beat process lifecycle."""

    state: BeatSyncState
    last_reconcile_epoch_seconds: float | None = None


async def create_beat_runtime_state(session: AsyncSession) -> CeleryBeatRuntimeState:
    """Create runtime state by loading all enabled jobs once at beat startup."""

    state = await load_enabled_schedule_state(session)
    return CeleryBeatRuntimeState(state=state)


def process_sync_message_once(
    runtime: CeleryBeatRuntimeState,
    payload: Mapping[str, Any],
    *,
    job_payload: Mapping[str, Any] | None = None,
) -> bool:
    """Apply one pub/sub sync payload to in-memory schedule state."""

    return apply_sync_event(runtime.state, payload, job_payload=job_payload)


def run_reconcile_cycle_once(
    runtime: CeleryBeatRuntimeState,
    rows: Iterable[SysCelery | Mapping[str, Any]],
    *,
    now_epoch_seconds: float,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one reconcile cycle and update runtime checkpoint timestamp."""

    next_last_reconcile, metadata = run_reconcile_once_if_due(
        runtime.state,
        rows,
        now_epoch_seconds=now_epoch_seconds,
        last_reconcile_epoch_seconds=runtime.last_reconcile_epoch_seconds,
        interval_seconds=interval_seconds,
    )
    runtime.last_reconcile_epoch_seconds = next_last_reconcile
    return metadata
