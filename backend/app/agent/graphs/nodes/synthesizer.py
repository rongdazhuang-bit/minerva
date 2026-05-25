"""Synthesizer node: merge sub-agent outputs into a final user-facing answer."""



from __future__ import annotations



import uuid



from langchain_core.messages import HumanMessage, SystemMessage

from langchain_core.runnables import RunnableConfig



from app.agent.domain.db.models import AgentRunNode

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event

from app.agent.graphs.deps import GraphDeps

from app.agent.graphs.state import AgentGraphState, StepResult

from app.agent.infrastructure import repository as agent_repo

from app.agent.infrastructure.chat_history import messages_with_user_input, split_trailing_user_message






async def _stream_model_text(

    deps: GraphDeps,

    messages: list,

    *,

    synth_node_id: uuid.UUID,

) -> str:

    """Stream model tokens to SSE and return the full concatenated text."""



    parts: list[str] = []

    last_usage = None

    async for chunk in deps.model.astream(messages):

        usage_metadata = getattr(chunk, "usage_metadata", None)

        if usage_metadata:

            last_usage = usage_metadata

        piece = getattr(chunk, "content", None)

        if not isinstance(piece, str) or not piece:

            continue

        parts.append(piece)

        if deps.emit_sse:

            await deps.emit_sse(

                build_sse_event(

                    event_type=AgentSseEventType.llm_delta,

                    run_id=deps.run_id,

                    session_id=deps.session_id,

                    payload={"channel": "assistant", "text": piece, "phase": "synthesizer"},

                )

            )

    if last_usage:

        await deps.record_llm_call_to_db(

            last_usage,

            parent_node_id=synth_node_id,

            phase="synthesizer",

        )

    return "".join(parts)





async def _invoke_model_text(

    deps: GraphDeps,

    messages: list,

    *,

    synth_node_id: uuid.UUID,

) -> str:

    """Call the model without SSE (sub-agents already streamed assistant text)."""



    resp = await deps.model.ainvoke(messages)

    await deps.record_llm_call_to_db(

        resp,

        parent_node_id=synth_node_id,

        phase="synthesizer",

    )

    content = getattr(resp, "content", None)

    return content.strip() if isinstance(content, str) else ""





async def _finalize_synthesizer_node(deps: GraphDeps, synth_node_id: uuid.UUID) -> None:

    """Roll up synthesizer phase usage onto the synthesizer.run node."""



    phase_slice = (deps.usage_tracker.document.get("by_phase") or {}).get("synthesizer") or {}

    if phase_slice:

        await deps.usage_tracker.rollup_children(

            deps.db,

            node_id=synth_node_id,

            child_usage=phase_slice,

        )

    synth_node = await deps.db.get(AgentRunNode, synth_node_id)

    if synth_node is not None:

        synth_node.status = "success"





def _format_subagent_blob(results: list[StepResult]) -> str:

    """Join step outputs for synthesizer merge prompts."""



    parts: list[str] = []

    for r in results:

        parts.append(f"[{r.get('skill_id')}] {r.get('output', '')}")

    return "\n\n".join(parts)





def resolve_final_answer_from_subagent_results(

    results: list[StepResult],

    *,

    user_message: str,

) -> str | None:

    """Return a final answer without a second LLM call when sub-agents already answered.



    A single successful step already streamed its reply via ``llm.delta``; re-synthesizing

    would duplicate the same text on the client.

    """



    if len(results) != 1:

        return None

    output = (results[0].get("output") or "").strip()

    return output if output else None





async def synthesizer_node(state: AgentGraphState, config: RunnableConfig) -> dict:

    """Produce final_answer from step results or direct model reply."""



    deps: GraphDeps = config["configurable"]["deps"]

    results = state.get("subagent_results") or []

    user_message = state.get("user_message", "")



    direct = resolve_final_answer_from_subagent_results(results, user_message=user_message)

    if direct is not None:

        return {"final_answer": direct}



    synth_node_id = uuid.uuid4()

    await agent_repo.insert_run_node(

        deps.db,

        node_id=synth_node_id,

        run_id=deps.run_id,

        parent_node_id=None,

        sequence_idx=800,

        node_type="synthesizer.run",

        node_name="synthesizer",

        status="running",

    )



    if not results:

        history = deps.conversation_messages or []

        if history:

            model_messages = history

        else:

            model_messages = messages_with_user_input([], user_message)

        text = await _stream_model_text(deps, model_messages, synth_node_id=synth_node_id)

        await _finalize_synthesizer_node(deps, synth_node_id)

        return {"final_answer": text}



    blob = _format_subagent_blob(results)

    sys = "你是助手。根据各步骤的执行结果，用简洁中文回答用户的原始问题。"

    history = deps.conversation_messages or []

    prior_turns, _ = split_trailing_user_message(history)

    text = await _invoke_model_text(

        deps,

        [

            *prior_turns,

            SystemMessage(content=sys),

            HumanMessage(content=f"用户问题：{user_message}\n\n步骤结果：\n{blob}"),

        ],

        synth_node_id=synth_node_id,

    )

    await _finalize_synthesizer_node(deps, synth_node_id)

    return {"final_answer": text}


