"""Orchestrate a single agent run: persist nodes/messages and stream SSE events."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentMessage
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure import skill_loader
from app.agent.infrastructure.redaction import redact_json
from app.agent.service.stream_accumulator import LlmStreamAccumulator
from app.config import settings
from app.exceptions import AppError
from app.llm.domain.models import ProviderKind
from app.llm.service.chat_service import chat_service as default_chat_service

log = logging.getLogger(__name__)


def _utc_iso() -> str:
    """Return current UTC time as ISO-8601 string with ``Z`` suffix."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sse_line(payload: dict[str, Any]) -> bytes:
    """Serialize one SSE ``data:`` frame."""

    return b"data: " + orjson.dumps(payload) + b"\n\n"


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


class AgentRunService:
    """Run one agent turn: DB writes, optional skills context, LLM stream, SSE output."""

    def __init__(self, *, chat: Any | None = None) -> None:
        self._chat = chat if chat is not None else default_chat_service

    async def run_stream_sse(
        self,
        session: AsyncSession,
        *,
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
        """Stream ``run_started`` … ``run_finished`` frames while persisting messages and nodes."""

        run_id = uuid.uuid4()
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
                yield _sse_line(
                    {
                        "v": 1,
                        "type": "error",
                        "run_id": str(run_id),
                        "ts": _utc_iso(),
                        "code": "agent.session_not_found",
                        "message": "会话不存在或不属于当前工作区。",
                    }
                )
                return

            yield _sse_line(
                {
                    "v": 1,
                    "type": "run_started",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "session_id": str(session_id),
                }
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
            await agent_repo.insert_run_node(
                session,
                node_id=root_id,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=_next_seq(),
                node_type="run.root",
                node_name="run",
                status="success",
                inputs_json=redact_json(
                    {"user_message": user_message[:2000], "skill_ids": skill_ids, "model": model},
                    max_bytes=settings.agent_json_snapshot_max_bytes,
                ),
            )

            idx_text = skill_loader.load_index_text()
            idx_node = uuid.uuid4()
            await agent_repo.insert_run_node(
                session,
                node_id=idx_node,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=_next_seq(),
                node_type="skill.index_load",
                node_name="INDEX.md",
                status="success",
                outputs_json={"chars": len(idx_text)},
            )

            for sid in skill_ids:
                sid_l = sid.strip().lower()
                if not sid_l:
                    continue
                try:
                    body = skill_loader.load_skill_markdown(sid_l)
                except OSError as e:
                    log.warning("skill load failed skill_id=%s err=%s", sid_l, e)
                    await agent_repo.insert_run_node(
                        session,
                        node_id=uuid.uuid4(),
                        run_id=run_id,
                        parent_node_id=None,
                        sequence_idx=_next_seq(),
                        node_type="skill.pack_load",
                        node_name=sid_l,
                        status="failed",
                        error_message=str(e),
                    )
                    continue
                await agent_repo.insert_run_node(
                    session,
                    node_id=uuid.uuid4(),
                    run_id=run_id,
                    parent_node_id=None,
                    sequence_idx=_next_seq(),
                    node_type="skill.pack_load",
                    node_name=sid_l,
                    status="success",
                    outputs_json={"chars": len(body)},
                )

            await agent_repo.append_agent_message(
                session,
                session_id=session_id,
                role="user",
                content=user_message,
                run_id=run_id,
            )

            rows = await agent_repo.list_agent_messages_ordered(session, session_id=session_id)
            api_messages: list[dict[str, Any]] = []
            skill_parts = [idx_text]
            for sid in skill_ids:
                sid_l = sid.strip().lower()
                if not sid_l:
                    continue
                try:
                    skill_parts.append(skill_loader.load_skill_markdown(sid_l))
                except OSError:
                    continue
            skill_block = "\n\n---\n\n".join(skill_parts)
            max_sys = 120_000
            if len(skill_block) > max_sys:
                skill_block = skill_block[:max_sys]
            api_messages.append(
                {
                    "role": "system",
                    "content": "以下技能说明供你参考：\n" + skill_block,
                }
            )
            for r in rows:
                api_messages.append(_message_row_to_openai(r))

            round_node = uuid.uuid4()
            await agent_repo.insert_run_node(
                session,
                node_id=round_node,
                run_id=run_id,
                parent_node_id=None,
                sequence_idx=_next_seq(),
                node_type="llm.round",
                node_name="round_1",
                status="running",
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
                },
            )

            await agent_repo.insert_run_node(
                session,
                node_id=uuid.uuid4(),
                run_id=run_id,
                parent_node_id=round_node,
                sequence_idx=1,
                node_type="llm.upstream_request",
                node_name="request",
                status="success",
                inputs_json=redact_json(
                    {"model": model, "temperature": temperature, "max_tokens": max_tokens},
                    max_bytes=settings.agent_json_snapshot_max_bytes,
                ),
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
                tools=None,
                tool_choice=None,
            ):
                for piece in acc.feed(chunk):
                    yield _sse_line(
                        {
                            "v": 1,
                            "type": "assistant_delta",
                            "run_id": str(run_id),
                            "ts": _utc_iso(),
                            "text": piece,
                        }
                    )

            tool_list = acc.build_tool_calls_list()
            if tool_list:
                yield _sse_line(
                    {
                        "v": 1,
                        "type": "error",
                        "run_id": str(run_id),
                        "ts": _utc_iso(),
                        "code": "agent.unexpected_tool_calls",
                        "message": "当前接口未启用工具调用，但上游返回了 tool_calls。",
                    }
                )
                await agent_repo.finalize_agent_run(
                    session,
                    run_id=run_id,
                    status="failed",
                    error_code="agent.unexpected_tool_calls",
                    error_message="unexpected tool_calls without tools",
                )
                return

            assistant = acc.build_assistant_message_dict()
            await agent_repo.append_agent_message(
                session,
                session_id=session_id,
                role="assistant",
                content=assistant.get("content"),
                tool_calls_json=assistant.get("tool_calls"),
                run_id=run_id,
            )

            await agent_repo.insert_run_node(
                session,
                node_id=uuid.uuid4(),
                run_id=run_id,
                parent_node_id=round_node,
                sequence_idx=2,
                node_type="llm.finish",
                node_name="finish",
                status="success",
                outputs_json={
                    "finish_reason": acc.finish_reason,
                    "chars": len(acc.full_text()),
                },
            )

            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="success",
                usage_json=None,
            )

            yield _sse_line(
                {
                    "v": 1,
                    "type": "run_finished",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "status": "success",
                }
            )
        except AppError as e:
            log.warning("agent run AppError run_id=%s code=%s", run_id, e.code)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code=e.code,
                error_message=str(e.message),
            )
            yield _sse_line(
                {
                    "v": 1,
                    "type": "error",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "code": e.code,
                    "message": str(e.message),
                }
            )
            yield _sse_line(
                {
                    "v": 1,
                    "type": "run_finished",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "status": "failed",
                }
            )
        except Exception as e:
            log.exception("agent run failed run_id=%s", run_id)
            await agent_repo.finalize_agent_run(
                session,
                run_id=run_id,
                status="failed",
                error_code="agent.internal_error",
                error_message=str(e),
            )
            yield _sse_line(
                {
                    "v": 1,
                    "type": "error",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "code": "agent.internal_error",
                    "message": "内部错误。",
                }
            )
            yield _sse_line(
                {
                    "v": 1,
                    "type": "run_finished",
                    "run_id": str(run_id),
                    "ts": _utc_iso(),
                    "status": "failed",
                }
            )


_default_agent_run_service = AgentRunService()


def get_agent_run_service() -> AgentRunService:
    """FastAPI 依赖：返回共享的 ``AgentRunService`` 实例。"""

    return _default_agent_run_service
