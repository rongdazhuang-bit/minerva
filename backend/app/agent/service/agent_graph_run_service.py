"""Orchestrate LangGraph agent runs with SSE v2 output."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.sse_v2 import (
    AgentSseEventType,
    SSE_DONE_LINE,
    build_sse_event,
)
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.main import build_main_graph
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.agent.infrastructure.event_mapper import map_langchain_stream_event
from app.agent.infrastructure.memory_store import AgentMemoryStore
from app.exceptions import AppError

log = logging.getLogger(__name__)


class AgentGraphRunService:
    """Run the main LangGraph and stream SSE v2 events."""

    def __init__(self) -> None:
        self._memory = AgentMemoryStore()
        self._graph = build_main_graph(checkpointer=None)

    async def run_stream_sse(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str,
        model_id: uuid.UUID,
        temperature: float | None = None,
        max_tokens: int | None = None,
        preferred_capabilities: list[str] | None = None,
    ) -> AsyncIterator[bytes]:
        """Execute one agent run and yield SSE v2 ``data:`` lines."""

        sse_buffer: list[bytes] = []

        async def emit(line: bytes) -> None:
            sse_buffer.append(line)

        try:
            sess = await agent_repo.get_agent_session(
                session, workspace_id=workspace_id, session_id=session_id
            )
            if sess is None:
                yield build_sse_event(
                    event_type=AgentSseEventType.run_error,
                    run_id=run_id,
                    session_id=session_id,
                    payload={"code": "agent.session_not_found", "message": "会话不存在。"},
                )
                yield SSE_DONE_LINE
                return

            model_row = await ChatModelFactory.get(
                session,
                workspace_id=workspace_id,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            yield build_sse_event(
                event_type=AgentSseEventType.run_started,
                run_id=run_id,
                session_id=session_id,
                payload={},
            )

            from app.sys.model_provider.infrastructure import repository as model_repo

            sys_row = await model_repo.get_for_workspace(
                session, workspace_id=workspace_id, model_id=model_id
            )
            model_name = sys_row.model_name if sys_row else "unknown"

            await agent_repo.create_agent_run(
                session,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                triggered_by=user_id,
                model=model_name,
                provider_kind=None,
                request_meta_json={
                    "model_id": str(model_id),
                    "preferred_capabilities": preferred_capabilities or [],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )

            await agent_repo.append_agent_message(
                session,
                session_id=session_id,
                role="user",
                content=user_message,
                run_id=run_id,
            )

            deps = GraphDeps(
                db=session,
                model=model_row,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
                memory_store=self._memory,
                emit_sse=emit,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            initial: AgentGraphState = {
                "session_id": session_id,
                "run_id": run_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "model_id": model_id,
                "user_message": user_message,
                "preferred_capabilities": preferred_capabilities or [],
                "plan": None,
                "current_step_index": 0,
                "retrieved_memories": [],
                "subagent_results": [],
                "final_answer": None,
            }

            config = {"configurable": {"deps": deps}}

            final_state = await self._graph.ainvoke(initial, config=config)

            while sse_buffer:
                yield sse_buffer.pop(0)

            final_answer = (final_state.get("final_answer") or "").strip()
            if final_answer:
                yield build_sse_event(
                    event_type=AgentSseEventType.message_final,
                    run_id=run_id,
                    session_id=session_id,
                    payload={"content": final_answer},
                )
                await agent_repo.append_agent_message(
                    session,
                    session_id=session_id,
                    role="assistant",
                    content=final_answer,
                    run_id=run_id,
                )

            await agent_repo.finalize_agent_run(
                session, run_id=run_id, status="success", usage_json=None
            )
            yield build_sse_event(
                event_type=AgentSseEventType.run_finished,
                run_id=run_id,
                session_id=session_id,
                payload={"status": "success"},
            )
            yield SSE_DONE_LINE
        except AppError as e:
            log.warning("agent v2 AppError run_id=%s code=%s", run_id, e.code)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code=e.code,
                error_message=str(e.message),
            )
            yield build_sse_event(
                event_type=AgentSseEventType.run_error,
                run_id=run_id,
                session_id=session_id,
                payload={"code": e.code, "message": str(e.message)},
            )
            yield build_sse_event(
                event_type=AgentSseEventType.run_finished,
                run_id=run_id,
                session_id=session_id,
                payload={"status": "failed"},
            )
            yield SSE_DONE_LINE
        except Exception as e:
            log.exception("agent v2 run failed run_id=%s", run_id)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code="agent.internal_error",
                error_message=str(e),
            )
            yield build_sse_event(
                event_type=AgentSseEventType.run_error,
                run_id=run_id,
                session_id=session_id,
                payload={"code": "agent.internal_error", "message": "内部错误。"},
            )
            yield build_sse_event(
                event_type=AgentSseEventType.run_finished,
                run_id=run_id,
                session_id=session_id,
                payload={"status": "failed"},
            )
            yield SSE_DONE_LINE


_default_agent_graph_run_service = AgentGraphRunService()


def get_agent_graph_run_service() -> AgentGraphRunService:
    """FastAPI dependency for ``AgentGraphRunService``."""

    return _default_agent_graph_run_service
