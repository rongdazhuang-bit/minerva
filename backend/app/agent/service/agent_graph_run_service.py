"""Orchestrate LangGraph agent runs with real-time SSE v2 output."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

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
from app.agent.infrastructure.chat_history import agent_rows_to_langchain
from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.agent.infrastructure.langgraph_checkpointer import get_langgraph_checkpointer
from app.agent.infrastructure.memory_store import AgentMemoryStore
from app.agent.service.memory_persist_service import schedule_persist_turn_memory_background
from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)


class AgentGraphRunService:
    """Run the main LangGraph and stream SSE v2 events in real time."""

    def __init__(self) -> None:
        self._memory = AgentMemoryStore()
        self._graph = None

    async def _get_graph(self):
        """Compile the main graph once (with optional checkpointer)."""

        if self._graph is None:
            checkpointer = await get_langgraph_checkpointer()
            self._graph = build_main_graph(checkpointer=checkpointer)
        return self._graph

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
        preferred_skills: list[str] | None = None,
    ) -> AsyncIterator[bytes]:
        """Execute one agent run; yield SSE v2 lines as the graph produces them."""

        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def emit(line: bytes) -> None:
            await queue.put(line)

        async def run_graph() -> None:
            try:
                sess = await agent_repo.get_agent_session(
                    session, workspace_id=workspace_id, session_id=session_id
                )
                if sess is None:
                    await emit(
                        build_sse_event(
                            event_type=AgentSseEventType.run_error,
                            run_id=run_id,
                            session_id=session_id,
                            payload={
                                "code": "agent.session_not_found",
                                "message": "会话不存在。",
                            },
                        )
                    )
                    return

                model_row = await ChatModelFactory.get(
                    session,
                    workspace_id=workspace_id,
                    model_id=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_started,
                        run_id=run_id,
                        session_id=session_id,
                        payload={},
                    )
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
                        "preferred_skills": preferred_skills or [],
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

                msg_rows = await agent_repo.list_agent_messages_ordered(
                    session, session_id=session_id
                )
                conversation_messages = agent_rows_to_langchain(
                    msg_rows,
                    max_messages=settings.agent_chat_history_message_limit,
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
                    conversation_messages=conversation_messages,
                )

                initial: AgentGraphState = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "model_id": model_id,
                    "user_message": user_message,
                    "preferred_skills": preferred_skills or [],
                    "plan": None,
                    "current_step_index": 0,
                    "retrieved_memories": [],
                    "subagent_results": [],
                    "final_answer": None,
                }

                graph = await self._get_graph()
                run_config = {
                    "configurable": {
                        "deps": deps,
                        "thread_id": f"{session_id}:{run_id}",
                    }
                }

                final_state = await graph.ainvoke(initial, config=run_config)

                final_answer = (final_state.get("final_answer") or "").strip()
                if final_answer:
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
                await session.commit()
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_finished,
                        run_id=run_id,
                        session_id=session_id,
                        payload={"status": "success"},
                    )
                )
                if final_answer:
                    schedule_persist_turn_memory_background(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run_id=run_id,
                        user_message=user_message,
                        final_answer=final_answer,
                        model_id=model_id,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
            except AppError as e:
                log.warning("agent v2 AppError run_id=%s code=%s", run_id, e.code)
                await agent_repo.finalize_agent_run(
                    session,
                    run_id=run_id,
                    status="failed",
                    error_code=e.code,
                    error_message=str(e.message),
                )
                await session.commit()
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_error,
                        run_id=run_id,
                        session_id=session_id,
                        payload={"code": e.code, "message": str(e.message)},
                    )
                )
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_finished,
                        run_id=run_id,
                        session_id=session_id,
                        payload={"status": "failed"},
                    )
                )
            except Exception as e:
                log.exception("agent v2 run failed run_id=%s", run_id)
                await agent_repo.finalize_agent_run(
                    session,
                    run_id=run_id,
                    status="failed",
                    error_code="agent.internal_error",
                    error_message=str(e),
                )
                await session.commit()
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_error,
                        run_id=run_id,
                        session_id=session_id,
                        payload={"code": "agent.internal_error", "message": "内部错误。"},
                    )
                )
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_finished,
                        run_id=run_id,
                        session_id=session_id,
                        payload={"status": "failed"},
                    )
                )
            finally:
                await emit(SSE_DONE_LINE)
                await queue.put(None)

        task = asyncio.create_task(run_graph())
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            await task


_default_agent_graph_run_service = AgentGraphRunService()


def get_agent_graph_run_service() -> AgentGraphRunService:
    """FastAPI dependency for ``AgentGraphRunService``."""

    return _default_agent_graph_run_service
