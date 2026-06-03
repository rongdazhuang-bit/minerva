"""mem0-backed memory persist strategy."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure import repository as agent_repo
from app.agent.memory.mem0.client import get_mem0_memory

log = get_logger(__name__)


class Mem0MemoryPersistStrategy:
    """Persist turn memory via mem0 ``add`` with infer/update."""

    async def persist_turn(
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        run_id: uuid.UUID,
        user_message: str,
        final_answer: str,
        model: BaseChatModel | None = None,
    ) -> None:
        """Write conversation turn to mem0; record run node status."""

        _ = model
        final = (final_answer or "").strip()
        user_text = (user_message or "").strip()
        if not final:
            return

        node_id = uuid.uuid4()
        try:
            await agent_repo.insert_run_node(
                session,
                node_id=node_id,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=900,
                node_type="memory.persist",
                node_name="persist",
                status="running",
            )
            messages = [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": final},
            ]

            def _add_sync() -> None:
                memory = get_mem0_memory()
                memory.add(
                    messages,
                    user_id=str(workspace_id),
                    run_id=str(session_id),
                    infer=True,
                    metadata={"source_run_id": str(run_id)},
                )

            await asyncio.to_thread(_add_sync)
            await agent_repo.insert_run_node(
                session,
                node_id=uuid.uuid4(),
                run_id=run_id,
                parent_node_id=node_id,
                sequence_idx=0,
                node_type="memory.persist",
                node_name="done",
                status="success",
                outputs_json={"backend": "mem0"},
            )
        except Exception as e:
            log.exception("mem0 memory.persist failed run_id={} err={}", run_id, e)
            await agent_repo.insert_run_node(
                session,
                node_id=uuid.uuid4(),
                run_id=run_id,
                parent_node_id=node_id,
                sequence_idx=1,
                node_type="memory.persist",
                node_name="failed",
                status="failed",
                error_message=str(e)[:500],
            )
