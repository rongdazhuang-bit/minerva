# Agent SSE：OpenAI 标准流 + minerva 编排扩展

**日期**：2026-05-16  
**状态**：已废止（2026-05-18）；由 **SSE v2** 替代，见 `2026-05-16-agent-langgraph-redesign-design.md` §5  
**替代**：`2026-05-15-agent-sse-persistence-design.md` §4 自定义 envelope

> **历史说明**：本文档记录中间态方案（OpenAI `chat.completion.chunk` + 根级 `minerva` v1）。该方案在 LangGraph 大改前曾定稿，**当前代码库已删除**相关实现。

## 目标（历史）

- Agent run 的 SSE **完全**采用 OpenAI `chat.completion.chunk` 线格式（`data: <json>` + `data: [DONE]`）。
- 上游模型 token（含 `reasoning_content` / `reasoning`）**原样透传**。
- 编排轨迹通过 chunk 根级扩展 **`minerva`**（schema `v=1`）推送。
- 响应头 `X-Minerva-Run-Id` 携带本次 run id。

## 当前实现（2026-05-18）

| 历史 spec | 当前代码 |
|-----------|----------|
| `sse_minerva.py` | **已删除** |
| `minerva-ui/src/api/openai-stream.ts` | **已删除** |
| `tool.start` / `tool.result` / `node.updated` | `tool.started` / `tool.finished`；`graph.node` 枚举存在但未发射 |
| OpenAI chunk 透传 | SSE v2 信封：`{ v: 2, type, run_id, session_id, ts, payload }`（`domain/sse_v2.py`） |
| reasoning 透传 | `llm.delta` + `payload.channel: "reasoning"`（`event_mapper.py`） |
| `X-Minerva-Run-Id` | **保留**（`api/v2/router.py`） |

## 非目标（历史，仍成立）

- 自定义 `{type: assistant_delta}` envelope（v1 已删除）。
- 将 reasoning 默认写回上游 messages（仅存 `agent_message` 侧展示逻辑）。
