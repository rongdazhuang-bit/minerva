"""Direct responder: stream a reply without Planner or ReAct sub-agent."""

from __future__ import annotations

import uuid

from langchain_core.runnables import RunnableConfig

from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.nodes.synthesizer import _stream_model_text
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.chat_history import messages_with_user_input


async def direct_responder_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Answer simple chat with one streaming LLM call (no plan / sub-agent)."""

    deps: GraphDeps = config["configurable"]["deps"]
    user_message = state.get("user_message", "")

    node_id = uuid.uuid4()
    async with deps.db_write() as session:
        await agent_repo.begin_run_node(
            session,
            node_id=node_id,
            run_id=deps.run_id,
            parent_node_id=None,
            sequence_idx=900,
            node_type="direct_responder.run",
            node_name="direct_responder",
        )

    history = deps.conversation_messages or []
    if history:
        model_messages = history
    else:
        model_messages = messages_with_user_input([], user_message)

    try:
        text = await _stream_model_text(deps, model_messages, synth_node_id=node_id)
        phase_slice = (deps.usage_tracker.document.get("by_phase") or {}).get("synthesizer") or {}
        async with deps.db_write() as session:
            if phase_slice:
                await deps.usage_tracker.rollup_children(
                    session,
                    node_id=node_id,
                    child_usage=phase_slice,
                )
            await agent_repo.finalize_run_node(
                session,
                node_id=node_id,
                status="success",
            )
        return {"final_answer": text}
    except Exception as exc:
        async with deps.db_write() as session:
            await agent_repo.finalize_run_node(
                session,
                node_id=node_id,
                status="failed",
                error_message=str(exc)[:500],
            )
        raise
