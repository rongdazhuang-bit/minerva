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
from app.agent.infrastructure.chat_history import build_conversation_messages_for_run
from app.agent.infrastructure.chat_model_factory import (
    ChatModelFactory,
    assert_model_supports_vision,
    model_supports_vision,
)
from app.agent.infrastructure.vision_messages import VisionAttachmentCache
from app.agent.service.agent_attachment_service import (
    build_attachment_rows_for_message,
    delete_storage_objects_for_rows,
    resolve_attachment_meta_for_run,
)
from app.files.service.workspace_file_service import WorkspaceFileService
from app.agent.infrastructure.reasoning_collector import ReasoningCollector
from app.agent.infrastructure.thinking_config import resolve_agent_thinking_config
from app.agent.infrastructure.langgraph_checkpointer import (
    get_langgraph_checkpointer,
    reset_langgraph_checkpointer,
)
from app.agent.infrastructure.run_db_writer import AgentRunDbWriter
from app.agent.memory.factory import create_memory_strategies
from app.agent.service.memory_persist_service import schedule_persist_turn_memory_background
from app.config import settings
from app.exceptions import AppError
from app.mcp.runtime.registry import mcp_registry
from app.sys.model_provider.infrastructure import repository as model_repo

log = get_logger(__name__)


def _vision_only_attachments(attachments: list[dict]) -> list[dict]:
    """Return attachment dicts with ``kind=image`` for vision graph injection."""

    return [item for item in attachments if item.get("kind") == "image"]


async def _attachment_dicts_from_message(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    meta_json: dict[str, Any] | list[Any] | None,
) -> list[dict]:
    """Load attachment metadata for one message from DB rows or legacy meta_json."""

    att_rows = await agent_repo.list_attachments_for_message_ids(
        session, message_ids=[message_id]
    )
    if att_rows:
        return [
            {
                "object_key": row.object_key,
                "file_name": row.file_name,
                "content_type": row.content_type,
                "size": row.size,
                "kind": row.kind,
            }
            for row in att_rows
        ]
    if not isinstance(meta_json, dict):
        return []
    raw_attachments = meta_json.get("attachments")
    if not isinstance(raw_attachments, list):
        return []
    return [
        dict(item)
        for item in raw_attachments
        if isinstance(item, dict) and item.get("object_key")
    ]


async def _prepare_assistant_finalize_meta(
    deps: GraphDeps,
    usage_snapshot: dict[str, Any] | None,
    *,
    status: str = "success",
) -> tuple[dict[str, Any], str | None]:
    """Build assistant ``meta_json`` / ``reasoning_text`` and emit reasoning SSE when enabled."""

    meta_payload: dict[str, Any] = {"streaming": False, "status": status}
    reasoning_text: str | None = None
    if usage_snapshot:
        meta_payload["usage"] = usage_snapshot
    if deps.reasoning_collector:
        await deps.reasoning_collector.mark_all_done(fallback_usage=usage_snapshot)
        reasoning_meta = deps.reasoning_collector.build_message_reasoning()
        if reasoning_meta is not None:
            meta_payload["reasoning"] = reasoning_meta
        reasoning_text = deps.reasoning_collector.build_message_reasoning_text()
    return meta_payload, reasoning_text


async def _persist_run_success_finalize(
    writer: AgentRunDbWriter,
    *,
    deps: GraphDeps,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    content: str,
    meta_payload: dict[str, Any],
    reasoning_text: str | None,
    usage_snapshot: dict[str, Any] | None,
) -> None:
    """Persist assistant message and run/session usage in one short transaction."""

    async def _write(db: AsyncSession) -> None:
        await agent_repo.update_agent_message(
            db,
            message_id=deps.assistant_message_id,
            content=content or None,
            meta_json=meta_payload,
            reasoning_text=reasoning_text,
        )
        await agent_repo.finalize_agent_run(
            db,
            run_id=run_id,
            status="success",
            usage_json=usage_snapshot or None,
        )
        session_delta = deps.usage_tracker.build_session_delta()
        if session_delta:
            await agent_repo.merge_session_usage_json(
                db,
                session_id=session_id,
                delta=session_delta,
            )

    await writer.run(_write)


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


def _resolve_persisted_assistant_content(deps: GraphDeps, final_state: AgentGraphState) -> str:
    """Prefer in-memory streamed assistant text; fall back to graph ``final_answer``."""

    streamed = deps.assistant_stream.get_text().strip()
    if streamed:
        return streamed
    return (final_state.get("final_answer") or "").strip()


async def _mark_assistant_message_terminal(
    writer: AgentRunDbWriter,
    *,
    deps: GraphDeps,
    status: str,
) -> None:
    """Finalize a placeholder assistant row after run failure (partial content allowed)."""

    content = deps.assistant_stream.get_text().strip()
    usage_snapshot = deps.usage_tracker.build_run_snapshot()
    meta_payload: dict[str, Any] = {"streaming": False, "status": status}
    if usage_snapshot:
        meta_payload["usage"] = usage_snapshot

    async def _write(db: AsyncSession) -> None:
        await agent_repo.update_agent_message(
            db,
            message_id=deps.assistant_message_id,
            content=content or None,
            meta_json=meta_payload,
        )

    await writer.run(_write)


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
        attachments: list[dict] | None = None,
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
                if sys_row is None:
                    await emit(
                        build_sse_event(
                            event_type=AgentSseEventType.run_error,
                            run_id=run_id,
                            session_id=session_id,
                            payload={
                                "code": "agent.model_not_found",
                                "message": "模型不存在。",
                            },
                        )
                    )
                    return

                run_attachments: list[dict] = []
                if attachments:
                    run_attachments = await resolve_attachment_meta_for_run(
                        session,
                        workspace_id=workspace_id,
                        items=attachments,
                    )
                    if any(item.get("kind") == "image" for item in run_attachments):
                        assert_model_supports_vision(sys_row)

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
                user_message_id: uuid.UUID | None = None
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
                    removed_attachments = await agent_repo.delete_attachments_for_messages_from_seq(
                        session,
                        session_id=session_id,
                        from_seq=truncate_from,
                    )
                    if removed_attachments:
                        await delete_storage_objects_for_rows(
                            session,
                            workspace_id=workspace_id,
                            rows=removed_attachments,
                        )
                    await agent_repo.delete_agent_messages_from_seq(
                        session,
                        session_id=session_id,
                        from_seq=truncate_from,
                    )
                else:
                    user_row = await agent_repo.append_agent_message(
                        session,
                        session_id=session_id,
                        role="user",
                        content=user_message,
                        run_id=run_id,
                        meta_json=None,
                    )
                    user_message_id = user_row.id
                    if run_attachments:
                        attachment_rows = await build_attachment_rows_for_message(
                            session,
                            workspace_id=workspace_id,
                            session_id=session_id,
                            message_id=user_row.id,
                            created_by=user_id,
                            items=run_attachments,
                        )
                        await agent_repo.insert_agent_message_attachments(
                            session, rows=attachment_rows
                        )

                assistant_row = await agent_repo.append_agent_message(
                    session,
                    session_id=session_id,
                    role="assistant",
                    content="",
                    run_id=run_id,
                    meta_json={"streaming": True},
                )
                assistant_message_id = assistant_row.id

                msg_rows = await agent_repo.list_agent_messages_ordered(
                    session, session_id=session_id
                )
                if is_regenerate and not run_attachments:
                    for row in reversed(msg_rows):
                        if (row.role or "").strip().lower() != "user":
                            continue
                        loaded = await _attachment_dicts_from_message(
                            session,
                            message_id=row.id,
                            meta_json=row.meta_json if isinstance(row.meta_json, dict) else None,
                        )
                        if loaded:
                            run_attachments = loaded
                            break
                vision_attachments = _vision_only_attachments(run_attachments)
                vision_cache = VisionAttachmentCache()
                file_service = WorkspaceFileService(session=session)
                supports_vision = model_supports_vision(sys_row.tags)
                att_rows = await agent_repo.list_attachments_for_session(
                    session, session_id=session_id
                )
                attachments_by_message_id: dict[uuid.UUID, list[dict]] = {}
                for att_row in att_rows:
                    attachments_by_message_id.setdefault(att_row.message_id, []).append(
                        {
                            "object_key": att_row.object_key,
                            "file_name": att_row.file_name,
                            "content_type": att_row.content_type,
                            "size": att_row.size,
                            "kind": att_row.kind,
                        }
                    )
                conversation_messages = await build_conversation_messages_for_run(
                    msg_rows,
                    workspace_id=workspace_id,
                    file_service=file_service,
                    cache=vision_cache,
                    include_vision_in_history=supports_vision,
                    max_messages=settings.agent_chat_history_message_limit,
                    attachments_by_message_id=attachments_by_message_id,
                )

                # Commit setup writes before the long graph run so agent_session row
                # locks from allocate_next_message_seq are not held for minutes.
                await session.commit()

                created_payload: dict[str, Any] = {
                    "assistant_message_id": str(assistant_message_id),
                }
                if user_message_id is not None:
                    created_payload["user_message_id"] = str(user_message_id)
                await emit(
                    build_sse_event(
                        event_type=AgentSseEventType.message_created,
                        run_id=run_id,
                        session_id=session_id,
                        payload=created_payload,
                    )
                )

                deps = GraphDeps(
                    db_writer=AgentRunDbWriter(),
                    model=model_row,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                    user_id=user_id,
                    memory_retrieve=self._memory_retrieve,
                    memory_persist=self._memory_persist,
                    assistant_message_id=assistant_message_id,
                    user_message_id=user_message_id,
                    reasoning_collector=reasoning_collector,
                    emit_sse=emit,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    conversation_messages=conversation_messages,
                    user_attachments=vision_attachments,
                    vision_cache=vision_cache,
                    model_supports_vision=supports_vision,
                )
                try:
                    mcp_tools, mcp_bundles, mcp_unavailable = await mcp_registry.resolve_langchain_tools(
                        workspace_id
                    )
                    deps.mcp_extra_tools = mcp_tools
                    deps.mcp_bundles = mcp_bundles
                    if mcp_unavailable:
                        await emit(
                            build_sse_event(
                                event_type=AgentSseEventType.mcp_tools_unavailable,
                                run_id=run_id,
                                session_id=session_id,
                                payload={
                                    "client_names": mcp_unavailable,
                                    "loaded_tool_count": len(mcp_tools),
                                },
                            )
                        )
                except Exception:
                    log.exception(
                        "failed to load MCP tools for workspace",
                        event="mcp.tools.load_failed",
                        workspace_id=str(workspace_id),
                    )
                    await emit(
                        build_sse_event(
                            event_type=AgentSseEventType.mcp_tools_unavailable,
                            run_id=run_id,
                            session_id=session_id,
                            payload={
                                "client_names": [],
                                "loaded_tool_count": 0,
                                "error": "mcp.tools.load_failed",
                            },
                        )
                    )

                initial: AgentGraphState = {
                    "session_id": session_id,
                    "run_id": run_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "model_id": model_id,
                    "user_message": user_message,
                    "user_attachments": vision_attachments,
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

                final_answer = _resolve_persisted_assistant_content(deps, final_state)
                usage_snapshot = deps.usage_tracker.build_run_snapshot()
                meta_payload, reasoning_text = await _prepare_assistant_finalize_meta(
                    deps,
                    usage_snapshot or None,
                    status="success",
                )
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
                try:
                    await _persist_run_success_finalize(
                        AgentRunDbWriter(),
                        deps=deps,
                        session_id=session_id,
                        run_id=run_id,
                        content=final_answer,
                        meta_payload=meta_payload,
                        reasoning_text=reasoning_text,
                        usage_snapshot=usage_snapshot or None,
                    )
                except Exception:
                    log.exception(
                        "agent run persist failed after run.finished",
                        event="agent.run.persist_failed",
                        run_id=str(run_id),
                        session_id=str(session_id),
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
                fail_writer = AgentRunDbWriter()
                if deps is not None:
                    await _mark_assistant_message_terminal(
                        fail_writer, deps=deps, status="failed"
                    )

                async def _fail_app_error(db: AsyncSession) -> None:
                    await agent_repo.finalize_agent_run(
                        db,
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
                                db,
                                session_id=session_id,
                                delta=session_delta,
                            )

                await fail_writer.run(_fail_app_error)
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
                fail_writer = AgentRunDbWriter()
                if deps is not None:
                    await _mark_assistant_message_terminal(
                        fail_writer, deps=deps, status="failed"
                    )

                async def _fail_internal(db: AsyncSession) -> None:
                    await agent_repo.finalize_agent_run(
                        db,
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
                                db,
                                session_id=session_id,
                                delta=session_delta,
                            )

                await fail_writer.run(_fail_internal)
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
                if deps is not None and deps.mcp_bundles:
                    await mcp_registry.close_tool_bundles(deps.mcp_bundles)
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
