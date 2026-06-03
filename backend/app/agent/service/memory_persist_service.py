"""Background long-term memory persistence after a successful agent run."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.agent.memory.factory import create_memory_strategies
from app.core.infrastructure.db.session import async_session_factory

log = get_logger(__name__)


async def persist_turn_memory(
    session: AsyncSession,
    *,
    model: BaseChatModel,
    memory_persist: object,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
) -> None:
    """Delegate to configured ``MemoryPersistStrategy``."""

    from app.agent.memory.protocols import MemoryPersistStrategy

    strategy: MemoryPersistStrategy = memory_persist  # type: ignore[assignment]
    await strategy.persist_turn(
        session,
        workspace_id=workspace_id,
        session_id=session_id,
        run_id=run_id,
        user_message=user_message,
        final_answer=final_answer,
        model=model,
    )


async def persist_turn_memory_background(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
    model_id: uuid.UUID,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    """Open a dedicated DB session and persist memory without blocking the SSE stream."""

    _, memory_persist = create_memory_strategies()
    async with async_session_factory() as session:
        try:
            model = await ChatModelFactory.get(
                session,
                workspace_id=workspace_id,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            await persist_turn_memory(
                session,
                model=model,
                memory_persist=memory_persist,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                user_message=user_message,
                final_answer=final_answer,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("memory.persist background failed run_id={}", run_id)


def schedule_persist_turn_memory_background(
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    user_message: str,
    final_answer: str,
    model_id: uuid.UUID,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    """Fire-and-forget background memory persist; logs task failures."""

    task = asyncio.create_task(
        persist_turn_memory_background(
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            user_message=user_message,
            final_answer=final_answer,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )

    def _done(t: asyncio.Task[None]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.error(
                "memory.persist background task crashed run_id={}",
                run_id,
                exc_info=exc,
            )

    task.add_done_callback(_done)
