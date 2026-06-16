"""Orchestrate LangGraph agent runs with real-time SSE v2 output."""

from __future__ import annotations

from app.core.log import get_logger
import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from psycopg_pool import PoolTimeout
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
from app.agent.infrastructure.reasoning_collector import ReasoningCollector
from app.agent.infrastructure.thinking_config import resolve_agent_thinking_config
from app.agent.infrastructure.langgraph_checkpointer import (
    get_langgraph_checkpointer,
    reset_langgraph_checkpointer,
)
from app.agent.memory.factory import create_memory_strategies
from app.agent.service.memory_persist_service import schedule_persist_turn_memory_background
from app.config import settings
from app.exceptions import AppError
from app.sys.model_provider.infrastructure import repository as model_repo

log = get_logger(__name__)


async def _finalize_run_usage(
    session: AsyncSession,
    *,
    deps: GraphDeps,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Write layered ``usage_json`` on the run and merge session totals."""

    usage_snapshot = deps.usage_tracker.build_run_snapshot()
    await agent_repo.finalize_agent_run(
        session,
        run_id=run_id,
        status=status,
        error_code=error_code,
        error_message=error_message,
        usage_json=usage_snapshot or None,
    )
    session_delta = deps.usage_tracker.build_session_delta()
    if session_delta:
        await agent_repo.merge_session_usage_json(
            session,
            session_id=session_id,
            delta=session_delta,
        )
    return usage_snapshot


async def _finalize_early_failed_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    error_code: str,
    error_message: str,
) -> None:
    """Mark a run failed when setup aborts after ``create_agent_run``."""

    await agent_repo.finalize_agent_run(
        session,
        run_id=run_id,
        status="failed",
        error_code=error_code,
        error_message=error_message,
        usage_json=None,
    )
    await session.commit()


async def _safe_rollback(session: AsyncSession) -> None:
    """Best-effort rollback when the async session is in a failed transaction state."""

    try:
        await session.rollback()
    except Exception:
        pass


class AgentGraphRunService:
    """Run the main LangGraph and stream SSE v2 events in real time."""

    def __init__(self) -> None:
        self._memory_retrieve, self._memory_persist = create_memory_strategies()
        self._graph = None

    async def _get_graph(self):
        """Compile the main graph once (with optional checkpointer)."""

        if self._graph is None:
            checkpointer = await get_langgraph_checkpointer()
            self._graph = build_main_graph(checkpointer=checkpointer)
        return self._graph

    async def _ainvoke_with_checkpoint_recovery(
        self,
        graph,
        initial: AgentGraphState,
        run_config: dict,
    ) -> AgentGraphState:
        """Run the graph; rebuild the checkpoint pool once on ``PoolTimeout``."""

        try:
            return await graph.ainvoke(initial, config=run_config)
        except PoolTimeout as e:
            log.warning(
                "checkpoint pool timeout during agent run, rebuilding pool: {}", e
            )
            await reset_langgraph_checkpointer()
            self._graph = None
            graph = await self._get_graph()
            return await graph.ainvoke(initial, config=run_config)

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
        regenerate_from_message_id: uuid.UUID | None = None,
        regenerate_last_assistant: bool = False,
        enable_thinking: bool | None = None,
    ) -> AsyncIterator[bytes]:
        """Execute one agent run; yield SSE v2 lines as the graph produces them.

        ``enable_thinking`` 为 ``None`` 时按 workspace 模型的 ``model_config`` 与全局
        ``agent_enable_thinking`` 决定是否向上游请求思考扩展参数。
        """

        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def emit(line: bytes) -> None:
            await queue.put(line)

        async def run_graph() -> None:
            deps: GraphDeps | None = None
            try:
                log.info(
                    "agent run started",
                    event="agent.run.started",
                    run_id=str(run_id),
                    session_id=str(session_id),
                )
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

                sys_row = await model_repo.get_for_workspace(
                    session, workspace_id=workspace_id, model_id=model_id
                )
                thinking = resolve_agent_thinking_config(
                    run_flag=enable_thinking,
                    model_config_raw=sys_row.model_config if sys_row else None,
                    settings=settings,
                )
                model_row = await ChatModelFactory.get(
                    session,
                    workspace_id=workspace_id,
                    model_id=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking=thinking,
                )

                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_started,
                        run_id=run_id,
                        session_id=session_id,
                        payload={},
                    )
                )

                reasoning_collector = ReasoningCollector(
                    run_id=run_id,
                    session_id=session_id,
                    emit_sse=emit,
                    thinking_enabled=thinking.enabled,
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
                        "enable_thinking": enable_thinking,
                    },
                )

                is_regenerate = bool(regenerate_from_message_id or regenerate_last_assistant)
                if is_regenerate:
                    truncate_from: int | None = None
                    if regenerate_from_message_id is not None:
                        target = await agent_repo.get_agent_message_for_session(
                            session,
                            workspace_id=workspace_id,
                            session_id=session_id,
                            message_id=regenerate_from_message_id,
                        )
                        if target is None:
                            await emit(
                                build_sse_event(
                                    event_type=AgentSseEventType.run_error,
                                    run_id=run_id,
                                    session_id=session_id,
                                    payload={
                                        "code": "agent.message_not_found",
                                        "message": "要重新生成的消息不存在。",
                                    },
                                )
                            )
                            await _finalize_early_failed_run(
                                session,
                                run_id=run_id,
                                error_code="agent.message_not_found",
                                error_message="要重新生成的消息不存在。",
                            )
                            return
                        if target.role != "assistant":
                            await emit(
                                build_sse_event(
                                    event_type=AgentSseEventType.run_error,
                                    run_id=run_id,
                                    session_id=session_id,
                                    payload={
                                        "code": "agent.regenerate_not_assistant",
                                        "message": "只能对助手回复重新生成。",
                                    },
                                )
                            )
                            await _finalize_early_failed_run(
                                session,
                                run_id=run_id,
                                error_code="agent.regenerate_not_assistant",
                                error_message="只能对助手回复重新生成。",
                            )
                            return
                        truncate_from = target.seq
                    else:
                        last_asst = await agent_repo.find_last_assistant_message(
                            session, session_id=session_id
                        )
                        if last_asst is None:
                            await emit(
                                build_sse_event(
                                    event_type=AgentSseEventType.run_error,
                                    run_id=run_id,
                                    session_id=session_id,
                                    payload={
                                        "code": "agent.regenerate_no_assistant",
                                        "message": "会话中尚无助手回复可重新生成。",
                                    },
                                )
                            )
                            await _finalize_early_failed_run(
                                session,
                                run_id=run_id,
                                error_code="agent.regenerate_no_assistant",
                                error_message="会话中尚无助手回复可重新生成。",
                            )
                            return
                        truncate_from = last_asst.seq
                    await agent_repo.delete_agent_messages_from_seq(
                        session,
                        session_id=session_id,
                        from_seq=truncate_from,
                    )
                else:
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

                # Commit setup writes before the long graph run so agent_session row
                # locks from allocate_next_message_seq are not held for minutes.
                await session.commit()

                deps = GraphDeps(
                    db=session,
                    model=model_row,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                    user_id=user_id,
                    memory_retrieve=self._memory_retrieve,
                    memory_persist=self._memory_persist,
                    reasoning_collector=reasoning_collector,
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

                final_state = await self._ainvoke_with_checkpoint_recovery(
                    graph, initial, run_config
                )

                final_answer = (final_state.get("final_answer") or "").strip()
                usage_snapshot = deps.usage_tracker.build_run_snapshot()
                if final_answer:
                    meta_payload: dict[str, Any] = {}
                    reasoning_text: str | None = None
                    if usage_snapshot:
                        meta_payload["usage"] = usage_snapshot
                    if deps.reasoning_collector:
                        await deps.reasoning_collector.mark_all_done(
                            fallback_usage=usage_snapshot,
                        )
                        reasoning_meta = deps.reasoning_collector.build_message_reasoning()
                        if reasoning_meta is not None:
                            meta_payload["reasoning"] = reasoning_meta
                        reasoning_text = deps.reasoning_collector.build_message_reasoning_text()
                    await agent_repo.append_agent_message(
                        session,
                        session_id=session_id,
                        role="assistant",
                        content=final_answer,
                        run_id=run_id,
                        meta_json=meta_payload if meta_payload else None,
                        reasoning_text=reasoning_text,
                    )

                usage_snapshot = await _finalize_run_usage(
                    session,
                    deps=deps,
                    session_id=session_id,
                    run_id=run_id,
                    status="success",
                )
                await session.commit()
                finished_payload: dict[str, Any] = {"status": "success"}
                if usage_snapshot:
                    finished_payload["usage"] = usage_snapshot
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.run_finished,
                        run_id=run_id,
                        session_id=session_id,
                        payload=finished_payload,
                    )
                )
                log.info(
                    "agent run finished",
                    event="agent.run.finished",
                    run_id=str(run_id),
                    session_id=str(session_id),
                    status="success",
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
                await _safe_rollback(session)
                log.warn(
                    "agent v2 AppError run_id={} code={}",
                    run_id,
                    e.code,
                    event="agent.run.failed",
                    run_id=str(run_id),
                    session_id=str(session_id),
                    code=e.code,
                )
                await agent_repo.finalize_agent_run(
                    session,
                    run_id=run_id,
                    status="failed",
                    error_code=e.code,
                    error_message=str(e.message),
                    usage_json=(deps.usage_tracker.build_run_snapshot() if deps else None),
                )
                if deps is not None:
                    session_delta = deps.usage_tracker.build_session_delta()
                    if session_delta:
                        await agent_repo.merge_session_usage_json(
                            session,
                            session_id=session_id,
                            delta=session_delta,
                        )
                await session.commit()
                failed_payload: dict[str, Any] = {"status": "failed"}
                if deps is not None:
                    snap = deps.usage_tracker.build_run_snapshot()
                    if snap:
                        failed_payload["usage"] = snap
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
                        payload=failed_payload,
                    )
                )
            except Exception as e:
                await _safe_rollback(session)
                log.exception(
                    "agent v2 run failed run_id={}",
                    run_id,
                    event="agent.run.failed",
                    run_id=str(run_id),
                    session_id=str(session_id),
                )
                await agent_repo.finalize_agent_run(
                    session,
                    run_id=run_id,
                    status="failed",
                    error_code="agent.internal_error",
                    error_message=str(e),
                    usage_json=(deps.usage_tracker.build_run_snapshot() if deps else None),
                )
                if deps is not None:
                    session_delta = deps.usage_tracker.build_session_delta()
                    if session_delta:
                        await agent_repo.merge_session_usage_json(
                            session,
                            session_id=session_id,
                            delta=session_delta,
                        )
                await session.commit()
                failed_payload: dict[str, Any] = {"status": "failed"}
                if deps is not None:
                    snap = deps.usage_tracker.build_run_snapshot()
                    if snap:
                        failed_payload["usage"] = snap
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
                        payload=failed_payload,
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
