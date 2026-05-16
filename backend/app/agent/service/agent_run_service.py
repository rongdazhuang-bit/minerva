"""Orchestrate a single agent run: persist nodes/messages and stream OpenAI-format SSE."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.sse_minerva import (
    MinervaChunkExtension,
    MinervaErrorPayload,
    MinervaNodeSnapshot,
    MinervaNodeStatus,
    MinervaStreamEventKind,
    MinervaToolSnapshot,
    utc_iso_now,
)
from app.agent.domain.db.models import AgentMessage
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure import skill_loader, skill_resolver, skill_tools
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.infrastructure.redaction import redact_json
from app.agent.infrastructure.sse_chunk_emitter import (
    SSE_DONE_LINE,
    emit_minerva_event,
    emit_openai_error,
    emit_upstream_chunk,
)
from app.agent.service.stream_accumulator import LlmStreamAccumulator
from app.config import settings
from app.exceptions import AppError
from app.llm.domain.models import ProviderKind
from app.llm.service.chat_service import chat_service as default_chat_service

log = logging.getLogger(__name__)


def _message_row_to_openai(row: AgentMessage) -> dict[str, Any]:
    """Map a persisted ``AgentMessage`` row to an OpenAI chat message dict."""

    msg: dict[str, Any] = {"role": row.role}
    if row.content is not None:
        msg["content"] = row.content
    if row.tool_calls_json is not None:
        msg["tool_calls"] = row.tool_calls_json
    if row.role == "tool":
        if row.tool_call_id:
            msg["tool_call_id"] = row.tool_call_id
        if row.tool_name:
            msg["name"] = row.tool_name
    return msg


def _preview_text(value: str, *, limit: int = 240) -> str:
    """Truncate long strings for SSE tool previews."""

    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _build_skill_system_messages(
    idx_text: str,
    effective_skill_ids: list[str],
) -> list[dict[str, Any]]:
    """Assemble system message(s) from INDEX and active skill packs."""

    skill_parts = [idx_text]
    for sid in effective_skill_ids:
        try:
            skill_parts.append(skill_loader.load_skill_markdown(sid))
        except OSError:
            continue
    skill_block = "\n\n---\n\n".join(skill_parts)
    max_sys = 120_000
    if len(skill_block) > max_sys:
        skill_block = skill_block[:max_sys]
    return [
        {
            "role": "system",
            "content": "以下技能说明供你参考：\n" + skill_block,
        }
    ]


async def _list_api_messages(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    idx_text: str,
    effective_skill_ids: list[str],
) -> list[dict[str, Any]]:
    """Rebuild OpenAI messages from DB plus skill system block."""

    rows = await agent_repo.list_agent_messages_ordered(session, session_id=session_id)
    api_messages: list[dict[str, Any]] = []
    api_messages.extend(_build_skill_system_messages(idx_text, effective_skill_ids))
    for r in rows:
        api_messages.append(_message_row_to_openai(r))
    return api_messages


def _node_extension(
    *,
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    node_id: uuid.UUID,
    parent_node_id: uuid.UUID | None,
    node_type: str,
    node_name: str,
    status: MinervaNodeStatus,
    sequence_idx: int | None,
) -> MinervaChunkExtension:
    """Build a ``node.updated`` minerva payload for one run node."""

    return MinervaChunkExtension(
        event=MinervaStreamEventKind.node_updated,
        run_id=run_id,
        ts=utc_iso_now(),
        session_id=session_id,
        node=MinervaNodeSnapshot(
            id=node_id,
            parent_node_id=parent_node_id,
            node_type=node_type,
            node_name=node_name,
            status=status,
            sequence_idx=sequence_idx,
        ),
    )


class AgentRunService:
    """Run one agent turn: DB writes, optional skills context, LLM stream, OpenAI SSE output."""

    def __init__(self, *, chat: Any | None = None) -> None:
        self._chat = chat if chat is not None else default_chat_service

    async def run_stream_sse(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str,
        skill_ids: list[str],
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> AsyncIterator[bytes]:
        """Stream OpenAI ``chat.completion.chunk`` frames plus ``minerva`` orchestration events."""

        seq_cursor = 0

        def _next_seq() -> int:
            nonlocal seq_cursor
            v = seq_cursor
            seq_cursor += 1
            return v

        try:
            sess = await agent_repo.get_agent_session(
                session, workspace_id=workspace_id, session_id=session_id
            )
            if sess is None:
                yield emit_openai_error(
                    message="会话不存在或不属于当前工作区。",
                    code="agent.session_not_found",
                )
                yield emit_minerva_event(
                    MinervaChunkExtension(
                        event=MinervaStreamEventKind.run_error,
                        run_id=run_id,
                        ts=utc_iso_now(),
                        session_id=session_id,
                        error=MinervaErrorPayload(
                            code="agent.session_not_found",
                            message="会话不存在或不属于当前工作区。",
                        ),
                    ),
                    model=model,
                )
                yield emit_minerva_event(
                    MinervaChunkExtension(
                        event=MinervaStreamEventKind.run_finished,
                        run_id=run_id,
                        ts=utc_iso_now(),
                        session_id=session_id,
                        status="failed",
                    ),
                    model=model,
                )
                yield SSE_DONE_LINE
                return

            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_started,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                ),
                model=model,
            )

            await agent_repo.create_agent_run(
                session,
                run_id=run_id,
                session_id=session_id,
                workspace_id=workspace_id,
                triggered_by=user_id,
                model=model,
                provider_kind=provider_kind.value,
                request_meta_json={
                    "skill_ids": skill_ids,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )

            root_id = uuid.uuid4()
            root_seq = _next_seq()
            await agent_repo.insert_run_node(
                session,
                node_id=root_id,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=root_seq,
                node_type="run.root",
                node_name="run",
                status="success",
                inputs_json=redact_json(
                    {"user_message": user_message[:2000], "skill_ids": skill_ids, "model": model},
                    max_bytes=settings.agent_json_snapshot_max_bytes,
                ),
            )
            yield emit_minerva_event(
                _node_extension(
                    run_id=run_id,
                    session_id=session_id,
                    node_id=root_id,
                    parent_node_id=None,
                    node_type="run.root",
                    node_name="run",
                    status=MinervaNodeStatus.success,
                    sequence_idx=root_seq,
                ),
                model=model,
            )

            idx_text = skill_loader.load_index_text()
            idx_node = uuid.uuid4()
            idx_seq = _next_seq()
            await agent_repo.insert_run_node(
                session,
                node_id=idx_node,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=idx_seq,
                node_type="skill.index_load",
                node_name="INDEX.md",
                status="success",
                outputs_json={"chars": len(idx_text)},
            )
            yield emit_minerva_event(
                _node_extension(
                    run_id=run_id,
                    session_id=session_id,
                    node_id=idx_node,
                    parent_node_id=None,
                    node_type="skill.index_load",
                    node_name="INDEX.md",
                    status=MinervaNodeStatus.success,
                    sequence_idx=idx_seq,
                ),
                model=model,
            )

            index_ids = skill_loader.parse_skill_ids_from_index(idx_text)
            effective_skill_ids = skill_resolver.resolve_effective_skill_ids(
                user_message=user_message,
                requested_skill_ids=skill_ids,
                index_skill_ids=index_ids,
            )
            resolve_mode = "explicit" if [s for s in skill_ids if s.strip()] else "auto"
            resolve_node = uuid.uuid4()
            resolve_seq = _next_seq()
            await agent_repo.insert_run_node(
                session,
                node_id=resolve_node,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=resolve_seq,
                node_type="skill.auto_resolve",
                node_name="resolve",
                status="success",
                outputs_json={
                    "mode": resolve_mode,
                    "matched_ids": effective_skill_ids,
                },
            )
            yield emit_minerva_event(
                _node_extension(
                    run_id=run_id,
                    session_id=session_id,
                    node_id=resolve_node,
                    parent_node_id=None,
                    node_type="skill.auto_resolve",
                    node_name="resolve",
                    status=MinervaNodeStatus.success,
                    sequence_idx=resolve_seq,
                ),
                model=model,
            )

            registry = skill_tools.load_tools_for_skills(
                effective_skill_ids,
                ctx=SkillToolContext(workspace_id=workspace_id),
            )
            tools_payload = registry.get_openai_tools_payload()
            tools_arg: list[dict[str, Any]] | None = tools_payload if tools_payload else None
            tool_choice = "auto" if tools_arg else None

            for sid in effective_skill_ids:
                sid_l = sid.strip().lower()
                if not sid_l:
                    continue
                node_id = uuid.uuid4()
                node_seq = _next_seq()
                try:
                    body = skill_loader.load_skill_markdown(sid_l)
                except OSError as e:
                    log.warning("skill load failed skill_id=%s err=%s", sid_l, e)
                    await agent_repo.insert_run_node(
                        session,
                        node_id=node_id,
                        run_id=run_id,
                        parent_node_id=None,
                        sequence_idx=node_seq,
                        node_type="skill.pack_load",
                        node_name=sid_l,
                        status="failed",
                        error_message=str(e),
                    )
                    yield emit_minerva_event(
                        _node_extension(
                            run_id=run_id,
                            session_id=session_id,
                            node_id=node_id,
                            parent_node_id=None,
                            node_type="skill.pack_load",
                            node_name=sid_l,
                            status=MinervaNodeStatus.failed,
                            sequence_idx=node_seq,
                        ),
                        model=model,
                    )
                    continue
                await agent_repo.insert_run_node(
                    session,
                    node_id=node_id,
                    run_id=run_id,
                    parent_node_id=None,
                    sequence_idx=node_seq,
                    node_type="skill.pack_load",
                    node_name=sid_l,
                    status="success",
                    outputs_json={"chars": len(body)},
                )
                yield emit_minerva_event(
                    _node_extension(
                        run_id=run_id,
                        session_id=session_id,
                        node_id=node_id,
                        parent_node_id=None,
                        node_type="skill.pack_load",
                        node_name=sid_l,
                        status=MinervaNodeStatus.success,
                        sequence_idx=node_seq,
                    ),
                    model=model,
                )

            await agent_repo.append_agent_message(
                session,
                session_id=session_id,
                role="user",
                content=user_message,
                run_id=run_id,
            )

            api_messages = await _list_api_messages(
                session,
                session_id=session_id,
                idx_text=idx_text,
                effective_skill_ids=effective_skill_ids,
            )

            round_labels = ("round_1", "round_2")
            for round_idx, round_name in enumerate(round_labels):
                if round_idx == 1 and not tools_arg:
                    break

                round_node = uuid.uuid4()
                round_seq = _next_seq()
                await agent_repo.insert_run_node(
                    session,
                    node_id=round_node,
                    run_id=run_id,
                    parent_node_id=None,
                    sequence_idx=round_seq,
                    node_type="llm.round",
                    node_name=round_name,
                    status="running",
                )
                yield emit_minerva_event(
                    _node_extension(
                        run_id=run_id,
                        session_id=session_id,
                        node_id=round_node,
                        parent_node_id=None,
                        node_type="llm.round",
                        node_name=round_name,
                        status=MinervaNodeStatus.running,
                        sequence_idx=round_seq,
                    ),
                    model=model,
                )

                if round_idx == 1:
                    api_messages = await _list_api_messages(
                        session,
                        session_id=session_id,
                        idx_text=idx_text,
                        effective_skill_ids=effective_skill_ids,
                    )

                ctx_node = uuid.uuid4()
                await agent_repo.insert_run_node(
                    session,
                    node_id=ctx_node,
                    run_id=run_id,
                    parent_node_id=round_node,
                    sequence_idx=0,
                    node_type="llm.context_snapshot",
                    node_name="context",
                    status="success",
                    outputs_json={
                        "message_count": len(api_messages),
                        "roles": [m.get("role") for m in api_messages],
                        "tool_names": registry.tool_names(),
                    },
                )
                yield emit_minerva_event(
                    _node_extension(
                        run_id=run_id,
                        session_id=session_id,
                        node_id=ctx_node,
                        parent_node_id=round_node,
                        node_type="llm.context_snapshot",
                        node_name="context",
                        status=MinervaNodeStatus.success,
                        sequence_idx=0,
                    ),
                    model=model,
                )

                req_node = uuid.uuid4()
                await agent_repo.insert_run_node(
                    session,
                    node_id=req_node,
                    run_id=run_id,
                    parent_node_id=round_node,
                    sequence_idx=1,
                    node_type="llm.upstream_request",
                    node_name="request",
                    status="success",
                    inputs_json=redact_json(
                        {
                            "model": model,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "tool_count": len(tools_arg or []),
                        },
                        max_bytes=settings.agent_json_snapshot_max_bytes,
                    ),
                )
                yield emit_minerva_event(
                    _node_extension(
                        run_id=run_id,
                        session_id=session_id,
                        node_id=req_node,
                        parent_node_id=round_node,
                        node_type="llm.upstream_request",
                        node_name="request",
                        status=MinervaNodeStatus.success,
                        sequence_idx=1,
                    ),
                    model=model,
                )

                acc = LlmStreamAccumulator()
                async for chunk in self._chat.stream_chunks_messages(
                    provider_kind=provider_kind,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=api_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools_arg,
                    tool_choice=tool_choice,
                ):
                    acc.feed(chunk)
                    yield emit_upstream_chunk(chunk)

                tool_list = acc.build_tool_calls_list()
                if tool_list and tools_arg is None:
                    err_code = "agent.unexpected_tool_calls"
                    err_msg = "当前接口未启用工具调用，但上游返回了 tool_calls。"
                    yield emit_openai_error(message=err_msg, code=err_code)
                    yield emit_minerva_event(
                        MinervaChunkExtension(
                            event=MinervaStreamEventKind.run_error,
                            run_id=run_id,
                            ts=utc_iso_now(),
                            session_id=session_id,
                            error=MinervaErrorPayload(code=err_code, message=err_msg),
                        ),
                        model=model,
                    )
                    await agent_repo.finalize_agent_run(
                        session,
                        run_id=run_id,
                        status="failed",
                        error_code=err_code,
                        error_message="unexpected tool_calls without tools",
                    )
                    yield emit_minerva_event(
                        MinervaChunkExtension(
                            event=MinervaStreamEventKind.run_finished,
                            run_id=run_id,
                            ts=utc_iso_now(),
                            session_id=session_id,
                            status="failed",
                        ),
                        model=model,
                    )
                    yield SSE_DONE_LINE
                    return

                if tool_list and tools_arg is not None:
                    if round_idx == 1:
                        err_code = "agent.tool_loop_exceeded"
                        err_msg = "工具调用轮次超过上限。"
                        yield emit_openai_error(message=err_msg, code=err_code)
                        yield emit_minerva_event(
                            MinervaChunkExtension(
                                event=MinervaStreamEventKind.run_error,
                                run_id=run_id,
                                ts=utc_iso_now(),
                                session_id=session_id,
                                error=MinervaErrorPayload(code=err_code, message=err_msg),
                            ),
                            model=model,
                        )
                        await agent_repo.finalize_agent_run(
                            session,
                            run_id=run_id,
                            status="failed",
                            error_code=err_code,
                            error_message=err_msg,
                        )
                        yield emit_minerva_event(
                            MinervaChunkExtension(
                                event=MinervaStreamEventKind.run_finished,
                                run_id=run_id,
                                ts=utc_iso_now(),
                                session_id=session_id,
                                status="failed",
                            ),
                            model=model,
                        )
                        yield SSE_DONE_LINE
                        return

                    assistant = acc.build_assistant_message_dict()
                    await agent_repo.append_agent_message(
                        session,
                        session_id=session_id,
                        role="assistant",
                        content=assistant.get("content"),
                        tool_calls_json=assistant.get("tool_calls"),
                        meta_json=acc.build_meta_json(),
                        run_id=run_id,
                    )

                    for tc in tool_list:
                        tc_id = str(tc.get("id") or "")
                        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                        tool_name = str(fn.get("name") or "")
                        args_json = str(fn.get("arguments") or "{}")
                        args_preview = _preview_text(args_json)

                        yield emit_minerva_event(
                            MinervaChunkExtension(
                                event=MinervaStreamEventKind.tool_start,
                                run_id=run_id,
                                ts=utc_iso_now(),
                                session_id=session_id,
                                tool=MinervaToolSnapshot(
                                    tool_call_id=tc_id,
                                    name=tool_name,
                                    arguments_preview=args_preview,
                                ),
                            ),
                            model=model,
                        )

                        tool_node = uuid.uuid4()
                        try:
                            result = await registry.invoke(tool_name, args_json)
                            tool_status = "success"
                        except Exception as e:
                            log.warning(
                                "tool invoke failed run_id=%s tool=%s err=%s",
                                run_id,
                                tool_name,
                                e,
                            )
                            result = f'{{"error": "{e}"}}'
                            tool_status = "failed"

                        await agent_repo.insert_run_node(
                            session,
                            node_id=tool_node,
                            run_id=run_id,
                            parent_node_id=None,
                            sequence_idx=_next_seq(),
                            node_type="tool.invocation",
                            node_name=f"tool:{tool_name}#{tc_id[:8]}",
                            status=tool_status,
                        )

                        await agent_repo.append_agent_message(
                            session,
                            session_id=session_id,
                            role="tool",
                            content=result,
                            tool_call_id=tc_id or None,
                            tool_name=tool_name or None,
                            run_id=run_id,
                        )

                        yield emit_minerva_event(
                            MinervaChunkExtension(
                                event=MinervaStreamEventKind.tool_result,
                                run_id=run_id,
                                ts=utc_iso_now(),
                                session_id=session_id,
                                tool=MinervaToolSnapshot(
                                    tool_call_id=tc_id,
                                    name=tool_name,
                                    arguments_preview=args_preview,
                                    result_preview=_preview_text(result),
                                ),
                            ),
                            model=model,
                        )

                    continue

                assistant = acc.build_assistant_message_dict()
                await agent_repo.append_agent_message(
                    session,
                    session_id=session_id,
                    role="assistant",
                    content=assistant.get("content"),
                    tool_calls_json=assistant.get("tool_calls"),
                    meta_json=acc.build_meta_json(),
                    run_id=run_id,
                )

                finish_node = uuid.uuid4()
                await agent_repo.insert_run_node(
                    session,
                    node_id=finish_node,
                    run_id=run_id,
                    parent_node_id=round_node,
                    sequence_idx=2,
                    node_type="llm.finish",
                    node_name="finish",
                    status="success",
                    outputs_json={
                        "finish_reason": acc.finish_reason,
                        "chars": len(acc.full_text()),
                        "reasoning_chars": len(acc.full_reasoning()),
                    },
                )
                yield emit_minerva_event(
                    _node_extension(
                        run_id=run_id,
                        session_id=session_id,
                        node_id=finish_node,
                        parent_node_id=round_node,
                        node_type="llm.finish",
                        node_name="finish",
                        status=MinervaNodeStatus.success,
                        sequence_idx=2,
                    ),
                    model=model,
                )
                break

            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="success",
                usage_json=None,
            )

            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_finished,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                    status="success",
                ),
                model=model,
            )
            yield SSE_DONE_LINE
        except AppError as e:
            log.warning("agent run AppError run_id=%s code=%s", run_id, e.code)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code=e.code,
                error_message=str(e.message),
            )
            yield emit_openai_error(message=str(e.message), code=e.code)
            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_error,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                    error=MinervaErrorPayload(code=e.code, message=str(e.message)),
                ),
                model=model,
            )
            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_finished,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                    status="failed",
                ),
                model=model,
            )
            yield SSE_DONE_LINE
        except Exception as e:
            log.exception("agent run failed run_id=%s", run_id)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code="agent.internal_error",
                error_message=str(e),
            )
            yield emit_openai_error(
                message="内部错误。",
                code="agent.internal_error",
                error_type="server_error",
            )
            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_error,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                    error=MinervaErrorPayload(
                        code="agent.internal_error",
                        message="内部错误。",
                    ),
                ),
                model=model,
            )
            yield emit_minerva_event(
                MinervaChunkExtension(
                    event=MinervaStreamEventKind.run_finished,
                    run_id=run_id,
                    ts=utc_iso_now(),
                    session_id=session_id,
                    status="failed",
                ),
                model=model,
            )
            yield SSE_DONE_LINE


_default_agent_run_service = AgentRunService()


def get_agent_run_service() -> AgentRunService:
    """FastAPI 依赖：返回共享的 ``AgentRunService`` 实例。"""

    return _default_agent_run_service
