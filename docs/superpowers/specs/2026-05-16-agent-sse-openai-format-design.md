# Agent SSE：OpenAI 标准流 + minerva 编排扩展

**日期**：2026-05-16  
**状态**：已定稿（实现中）  
**替代**：`2026-05-15-agent-sse-persistence-design.md` §4 自定义 envelope

## 目标

- Agent run 的 SSE **完全**采用 OpenAI `chat.completion.chunk` 线格式（`data: <json>` + `data: [DONE]`）。
- 上游模型 token（含 `reasoning_content` / `reasoning`）**原样透传**。
- 编排轨迹通过 chunk 根级扩展 **`minerva`**（schema `v=1`）推送；类型由 Pydantic / TypeScript 对象类约束。
- 响应头 `X-Minerva-Run-Id` 携带本次 run id。

## minerva 扩展（v1）

见 `backend/app/agent/domain/sse_minerva.py` 与 `minerva-ui/src/api/openai-stream.ts`。

事件：`run.started` | `run.finished` | `run.error` | `node.updated` | `tool.start` | `tool.result`。

## 非目标

- 自定义 `{type: assistant_delta}` envelope（已删除）。
- 将 reasoning 默认写回上游 messages（仅存 `agent_message.meta_json`）。
