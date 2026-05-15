# Agent（技能包 + LLM 工具流式 + 会话持久化 + 细粒度节点）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `backend/app/agent/` 交付可复用的智能体运行能力：从 `skills/INDEX.md` 与子 skill 装配文档与 tools、经扩展后的 **`app/llm` 真流式**调用模型（含 function calling 多轮）、**默认单条 SSE** 输出统一事件 envelope；持久化 **`agent_session` / `agent_message` / `agent_run` / `agent_run_node` 树**以支持跨请求续写与类 Dify 节点审计；对外提供工作区鉴权 HTTP API，并保留结构化应用日志（`run_id`、脱敏）。

**Architecture:** **方案 3**：`llm` 的 `ChatCallParams` + `OpenAICompatibleStrategy` 扩展 `tools` / `tool_choice` 与 **OpenAI 形态 `messages`（`list[dict[str, Any]]`）**；流式路径把上游 chunk **原样或近原样**迭代给上层。`agent` 的 `AgentRunService` 负责 tool 循环、**SSE 事件发射**、**节点树写入**与 **`agent_message` 续写**；技能装载与注册在 `agent/infrastructure`。数据库表通过 SQLAlchemy 模型 + 既有 `create_missing_tables` 的 `_import_models()` 注册。**注释与表单等仓库惯例**见 `.cursor/skills/code-comments/SKILL.md`（新增 Python 类/公开方法需有说明性 docstring）。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, PostgreSQL + `JSONB`, OpenAI Python SDK（异步），pytest + httpx `AsyncClient`，orjson（与现有 `llm` 一致处可复用）。

**设计依据:** `docs/superpowers/specs/2026-05-15-agent-sse-persistence-design.md`

**提交策略说明:** 下列步骤中的 **Commit** 为建议原子；若协作者约定「仅在被要求时提交」，可将多个 Task 合并后再一次性提交（不要跳过已通过的测试）。

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/app/config.py` | 新增 agent 相关配置项：`agent_node_stream_segment_max_chars`、`agent_node_stream_segment_max_chunks`、`agent_node_stream_segment_max_rows`、`agent_json_snapshot_max_bytes`、`agent_max_tool_rounds`、单工具超时秒数等（名称可略调，集中一处） |
| `backend/app/llm/domain/models.py` | `ChatCallParams` 增加 `tools`、`tool_choice`；`messages` 元素放宽为 `dict[str, Any]`（仍兼容仅 `role`+`content`） |
| `backend/app/llm/strategies/openai_compatible.py` | `_completion_kwargs` 合并 `tools`/`tool_choice`；日志仍禁止打印完整 api_key |
| `backend/app/llm/strategies/volcengine_placeholder.py`、`aliyun_placeholder.py` | 构造函数签名若受 `ChatCallParams` 影响：保持可实例化；`complete`/`stream` 仍抛未实现 |
| `backend/app/llm/service/chat_service.py` | `complete` / `stream_chunks` 透传新字段到 `ChatCallParams` |
| `backend/app/llm/strategies/base.py` | 若使用 `Protocol`：流式签名与实现一致（`async def` generator） |
| `backend/app/agent/__init__.py` | 包导出（按需最小） |
| `backend/app/agent/domain/db/models.py` | ORM：`AgentSession`、`AgentMessage`、`AgentRun`、`AgentRunNode` |
| `backend/app/agent/domain/__init__.py` | 占位或导出 |
| `backend/app/agent/domain/sse_events.py`（或 `envelope.py`） | SSE JSON envelope 的 Pydantic 模型与 `type` 字面量常量 |
| `backend/app/agent/domain/node_types.py` | `node_type` 字符串常量（`run.root`、`skill.index_load`、`llm.round`…） |
| `backend/app/agent/infrastructure/skill_loader.py` | 读取 `skills/INDEX.md`、解析子 skill 列表、加载 `SKILL.md` 全文到内存 |
| `backend/app/agent/infrastructure/tool_registry.py` | `name -> (json_schema, async handler)`；仅白名单 |
| `backend/app/agent/infrastructure/redaction.py` | 递归脱敏 key（如 `api_key`、`authorization`）+ JSONB 截断 |
| `backend/app/agent/infrastructure/repository.py` | session/message/run/node 的 insert/select/seq 分配（`next_seq(session_id)` 用 `SELECT coalesce(max(seq),0)+1 ... FOR UPDATE` 或等价事务策略） |
| `backend/app/agent/service/agent_run_service.py` | 主编排：建 run、写节点树、流式循环、落库 message |
| `backend/app/agent/service/stream_accumulator.py`（可选独立文件） | 从 OpenAI 流 chunk 累积 `content` 与 `tool_calls` 片段直至完整 |
| `backend/app/agent/api/schemas.py` | `CreateSessionBody`、`CreateRunBody`（用户消息、provider、base_url、api_key、model、temperature、max_tokens、`skill_ids` 等） |
| `backend/app/agent/api/router.py` | `POST /workspaces/{workspace_id}/agent/sessions`、`POST .../sessions/{session_id}/runs`（SSE） |
| `backend/app/core/api/router.py` | `include_router(agent_router)` |
| `backend/app/core/infrastructure/db/bootstrap.py` | `_import_models()` 增加 `import app.agent.domain.db.models` |
| `backend/app/agent/skills/INDEX.md` | 总索引示例 + 指向示例子 skill（可最小占位） |
| `backend/app/agent/skills/example_echo/SKILL.md`、`tools.py` | 演示用 echo tool（仅开发/测试启用的技能 id，路由层可强制仅 workspace dev）— **若不想暴露示例 tool 到生产**，改为测试里 `registry.register` 假 tool，skills 目录只保留文档 |
| `backend/tests/test_llm_tools_params.py`（新建） | `OpenAICompatibleStrategy._completion_kwargs` 或 `complete` mock 断言 kwargs 含 `tools` |
| `backend/tests/test_agent_run_service.py`（新建） | mock `chat_service.stream_chunks`，断言 SSE 行与节点写入顺序（可用内存 fake repo） |
| `backend/tests/test_agent_api.py`（新建） | 401、403；注册+带 token 调 session 创建（需 DB：与 `test_llm.py` 同风格 `AsyncClient`） |

---

## Task 1: 配置项

**Files:**

- Modify: `backend/app/config.py`

- [ ] **Step 1: 在 `Settings` 中增加字段**

在 `class Settings(BaseSettings):` 内增加（默认值与 spec §5.4 对齐，可用 `Field` 描述）：

```python
from pydantic import Field

agent_node_stream_segment_max_chars: int = Field(default=2048, ge=256)
agent_node_stream_segment_max_chunks: int = Field(default=50, ge=1)
agent_node_stream_segment_max_rows: int = Field(default=500, ge=10)
agent_json_snapshot_max_bytes: int = Field(default=65536, ge=4096)
agent_max_tool_rounds: int = Field(default=16, ge=1)
agent_tool_timeout_seconds: float = Field(default=60.0, ge=1.0)
```

若项目从环境变量加载，为每个字段加 `validation_alias` 或统一前缀（与现有 `settings` 风格一致即可）。

- [ ] **Step 2: 校验 import**

Run: `cd d:\ityeahProjects\minerva\backend && python -c "from app.config import settings; print(settings.agent_max_tool_rounds)"`  
Expected: `16`（或你改过的默认值）。

- [ ] **Step 3: Commit（可选）**

```bash
git add backend/app/config.py
git commit -m "feat(config): add agent persistence and streaming limits"
```

---

## Task 2: `llm` — `ChatCallParams` 与策略 kwargs

**Files:**

- Modify: `backend/app/llm/domain/models.py`
- Modify: `backend/app/llm/strategies/openai_compatible.py`

- [ ] **Step 1: 扩展 `ChatCallParams`**

将 `messages` 改为更宽类型并增加可选 tools（保持默认工厂为空列表）：

```python
from typing import Any

class ChatCallParams(BaseModel):
    base_url: str = Field(description="OpenAI-compatible root, e.g. https://host/v1 for LiteLLM.")
    api_key: str
    model: str
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="OpenAI-style chat messages (subset to full tool schema).",
    )
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
```

- [ ] **Step 2: `_completion_kwargs` 合并 tools**

在 `openai_compatible.py` 的 `_completion_kwargs` 末尾追加：

```python
    if params.tools is not None:
        kwargs["tools"] = params.tools
    if params.tool_choice is not None:
        kwargs["tool_choice"] = params.tool_choice
    return kwargs
```

- [ ] **Step 3: 新增/更新单测**

新建 `backend/tests/test_llm_tools_params.py`：

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.domain.models import ChatCallParams
from app.llm.strategies.openai_compatible import OpenAICompatibleStrategy


@pytest.mark.asyncio
async def test_openai_compatible_complete_passes_tools_to_create() -> None:
    tools = [{"type": "function", "function": {"name": "echo", "parameters": {"type": "object", "properties": {}}}}]
    fake = MagicMock()
    fake.model_dump = MagicMock(return_value={"id": "x", "choices": []})
    create_mock = AsyncMock(return_value=fake)
    mock_client = MagicMock()
    mock_client.chat.completions.create = create_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm.strategies.openai_compatible.AsyncOpenAI", return_value=mock_cm):
        strat = OpenAICompatibleStrategy()
        await strat.complete(
            ChatCallParams(
                base_url="http://litellm/v1",
                api_key="sk",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
                tool_choice="auto",
            )
        )
    kwargs = create_mock.await_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"
```

Run: `cd d:\ityeahProjects\minerva\backend && pytest tests/test_llm_tools_params.py -v`  
Expected: **PASS**

- [ ] **Step 4: 全量回归 `test_llm.py`**

Run: `pytest tests/test_llm.py -v`  
Expected: **PASS**（若 `ChatCallParams` 类型放宽导致 mypy 严格失败，以仓库当前 CI 为准修复）。

- [ ] **Step 5: Commit（可选）**

```bash
git add backend/app/llm/domain/models.py backend/app/llm/strategies/openai_compatible.py backend/tests/test_llm_tools_params.py
git commit -m "feat(llm): pass tools and tool_choice to OpenAI-compatible completions"
```

---

## Task 3: `ChatService` 透传 tools（阻塞 + 流）

**Files:**

- Modify: `backend/app/llm/service/chat_service.py`

- [ ] **Step 1: `complete` 与 `stream_chunks` 签名**

为 `complete`、`stream_chunks`、`stream_sse_lines` 增加可选参数 `tools: list[dict[str, Any]] | None = None`、`tool_choice: str | dict[str, Any] | None = None`，构造 `ChatCallParams` 时传入。

示例（`complete` 内）：

```python
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
```

**注意**：`build_openai_messages` 返回 `list[dict[str,str]]`，在 `messages` 已改为 `Any` 后可直接传入；**agent 路径**后续会传入 **已含 system/tool 的** `messages`，需要新增重载方法 **`complete_messages`** / **`stream_chunks_messages`**（仅 agent 调用）以避免重复拼接 `user_prompt` — 在本 Task 可选实现为：

```python
    async def complete_messages(
        self,
        *,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strategy = get_strategy(provider_kind)
        params = ChatCallParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        ...
```

将原有重试循环提取为 `_complete_with_retry(self, strategy, params)` 避免复制粘贴。

- [ ] **Step 2: pytest**

为 `complete_messages` 增加 mock 策略单测（与 `test_chat_service_complete_retries_on_rate_limit` 同模式），断言 `params.tools` 传入。

- [ ] **Step 3: Commit（可选）**

```bash
git add backend/app/llm/service/chat_service.py backend/tests/test_llm.py
git commit -m "feat(llm): chat_service supports tools and raw message list"
```

---

## Task 4: Agent ORM 模型

**Files:**

- Create: `backend/app/agent/domain/db/models.py`
- Create: `backend/app/agent/domain/db/__init__.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`

- [ ] **Step 1: 定义四张表（与 spec §5–§6 对齐）**

在 `models.py` 使用与 `SysCelery` / `OcrFileLog` 相同风格：`UUID`、`DateTime(timezone=True)`、`JSONB`、`ForeignKey(..., ondelete="CASCADE")`、`Mapped[...]`。

要点：

- `AgentRunNode.parent_node_id`：`ForeignKey("agent_run_node.id", ondelete="SET NULL")` 自引用。
- 唯一约束：`UniqueConstraint("session_id", "seq", name="uq_agent_message_session_seq")`；`UniqueConstraint("run_id", "parent_node_id", "sequence_idx", name="uq_agent_run_node_run_parent_seq")` — PostgreSQL 允许多个 `NULL` parent 时唯一性行为需验证；若 `parent_node_id` 全为 NULL 的根节点冲突，可改为根节点使用 **虚拟父** 或 **部分唯一索引**（实现时以迁移可行为准）。
- `agent_run.id` 即 `run_id`，与 SSE 对齐。

- [ ] **Step 2: 注册 bootstrap**

在 `_import_models()` 末尾加：

```python
    import app.agent.domain.db.models  # noqa: F401
```

- [ ] **Step 3: 启动建表验证（本地有 PG 时）**

Run: `cd backend && python -c "from app.core.infrastructure.db.bootstrap import _import_models; _import_models(); from app.core.infrastructure.db.base import Base; print('agent_session' in Base.metadata.tables)"`  
Expected: `True`

- [ ] **Step 4: Commit（可选）**

```bash
git add backend/app/agent/domain/db/models.py backend/app/agent/domain/db/__init__.py backend/app/core/infrastructure/db/bootstrap.py
git commit -m "feat(agent): add ORM models for session, message, run, run nodes"
```

---

## Task 5: Repository + 事务辅助

**Files:**

- Create: `backend/app/agent/infrastructure/repository.py`

- [ ] **Step 1: 实现最小接口**

异步函数（名称可微调，但 service 只依赖此处）：

- `create_session(...)` → `AgentSession`
- `create_run(...)` → `AgentRun`
- `append_user_message(session_id, content, *, run_id)` → 分配 `seq` 并 insert
- `append_assistant_message(...)`、`append_tool_message(...)`
- `list_messages_for_session(session_id) -> list[AgentMessage]` 按 `seq` 升序
- `insert_node(...)`、`finalize_run(run_id, status, error...)`

`next_seq` 必须在 **同一事务** 内 `SELECT max(seq) ...` 或使用 PostgreSQL `INSERT ... RETURNING` 结合子查询；禁止并发下重复 `seq`。

- [ ] **Step 2: 单测（可选 sqlite 内存 vs 项目 PG fixture）**

若仓库尚无 async PG fixture，先用 **fake in-memory** 协议类（`Protocol`）在 `test_agent_run_service` 里测业务；本 Task 仅保证 `repository.py` **import 无循环依赖**：

Run: `python -c "from app.agent.infrastructure import repository as r; print('ok')"`  
Expected: `ok`

- [ ] **Step 3: Commit（可选）**

```bash
git add backend/app/agent/infrastructure/repository.py
git commit -m "feat(agent): persistence repository for sessions and runs"
```

---

## Task 6: SkillLoader + ToolRegistry + redaction

**Files:**

- Create: `backend/app/agent/infrastructure/skill_loader.py`
- Create: `backend/app/agent/infrastructure/tool_registry.py`
- Create: `backend/app/agent/infrastructure/redaction.py`

- [ ] **Step 1: `SkillLoader`**

- 根路径：`Path(__file__).resolve().parents[1] / "skills"`（指向 `backend/app/agent/skills`）。
- `load_index() -> str` 读取 `INDEX.md`；`list_skill_ids() -> list[str]`：解析规则写清——**首期**可用约定：`INDEX.md` 中用 Markdown 列表 `- skill_id` 列出子目录名；解析失败抛 `AppError`（业务码如 `agent.skill.index_invalid`）。

- [ ] **Step 2: `ToolRegistry`**

```python
class ToolRegistry:
    def register(self, name: str, schema: dict, handler: Callable[..., Awaitable[Any]]) -> None: ...
    def get_openai_tools_payload(self) -> list[dict[str, Any]]: ...
    async def invoke(self, name: str, arguments_json: str) -> str: ...
```

`get_openai_tools_payload` 返回 `[{"type":"function","function":{"name":...,"description":...,"parameters":...}}]`。

- [ ] **Step 3: `redaction`**

```python
def redact_json(value: Any, *, max_bytes: int) -> Any: ...
```

递归将键名匹配 `(?i)(api_key|authorization|password|secret)` 的值替换为 `"***"`；最后对序列化字节长度截断。

- [ ] **Step 4: 单测 `tests/test_agent_redaction.py`**

```python
from app.agent.infrastructure.redaction import redact_json

def test_redact_strips_secrets():
    out = redact_json({"api_key": "sk-xxx", "nested": {"Authorization": "Bearer z"}}, max_bytes=10_000)
    assert out["api_key"] == "***"
    assert out["nested"]["Authorization"] == "***"
```

Run: `pytest tests/test_agent_redaction.py -v` → **PASS**

- [ ] **Step 5: Commit（可选）**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/app/agent/infrastructure/tool_registry.py backend/app/agent/infrastructure/redaction.py backend/tests/test_agent_redaction.py
git commit -m "feat(agent): skill loader, tool registry, and json redaction"
```

---

## Task 7: 流式累积器（OpenAI chunk → 完整 assistant + tool_calls）

**Files:**

- Create: `backend/app/agent/service/stream_accumulator.py`

- [ ] **Step 1: 状态机**

类 `LlmStreamAccumulator`：

- 方法 `feed(chunk: dict[str, Any]) -> list[str]`：返回本轮应 **立刻转发给前端的文本增量**列表（从 `choices[0].delta.content` 提取；可能为片段或 `None`）。
- 属性 `finish_reason: str | None`
- 方法 `build_assistant_message_dict() -> dict[str, Any]`：合并 `content` 与 `tool_calls`（按 OpenAI 消息格式 `{role, content?, tool_calls?}`）。

`tool_calls` 增量合并逻辑：对 `choices[0].delta.tool_calls` 列表，按 `index` 合并 `id`、`function.name`、`function.arguments` 字符串拼接。

- [ ] **Step 2: 单测构造假 chunk**

`tests/test_agent_stream_accumulator.py` 中模拟两个 chunk：第一个 `delta.tool_calls=[{index:0, id:"call_1", function:{name:"echo", arguments:""}}]`，第二个补充 `arguments:'{\"x\":1}'`；断言 `build_assistant_message_dict()` 中 `tool_calls` 完整。

Run: `pytest tests/test_agent_stream_accumulator.py -v` → **PASS**

- [ ] **Step 3: Commit（可选）**

```bash
git add backend/app/agent/service/stream_accumulator.py backend/tests/test_agent_stream_accumulator.py
git commit -m "feat(agent): accumulate OpenAI stream chunks including tool_calls"
```

---

## Task 8: `AgentRunService`（核心编排）

**Files:**

- Create: `backend/app/agent/service/agent_run_service.py`
- Create: `backend/app/agent/service/__init__.py`

- [ ] **Step 1: 依赖注入形状**

```python
class AgentRunService:
    def __init__(self, *, chat_service: ChatService, settings: Settings) -> None:
        self._chat = chat_service
        self._settings = settings
```

对外方法：

```python
    async def run_stream_sse(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        user_text: str,
        provider_kind: ProviderKind,
        base_url: str,
        api_key: str,
        model: str,
        skill_ids: list[str],
        temperature: float | None,
        max_tokens: int | None,
    ) -> AsyncIterator[bytes]:
        ...
```

内部顺序（与 spec 对齐）：

1. `create_run`；yield `run_started`。
2. 写 `run.root`、`skill.index_load`、各 `skill.pack_load` 节点。
3. `append_user_message`。
4. 从 DB `list_messages` 组装 `messages: list[dict[str, Any]]`；拼接 skill 文档为 **额外 system 消息**（注意总长度限制，超限写 `log` 事件并截断）。
5. Tool 循环 `for round_ix in range(agent_max_tool_rounds)`：
   - 创建 `llm.round` 节点与子节点 `llm.context_snapshot`、`llm.upstream_request`。
   - 创建 `LlmStreamAccumulator`；`async for chunk in self._chat.stream_chunks_messages(...)`：
     - 将文本增量封装 `assistant_delta` SSE；
     - 按 **segment 策略** 写多条 `llm.stream_segment` 节点（读 `settings.agent_node_stream_segment_*`）。
   - `llm.tool_calls_parsed` / `llm.finish`。
   - 若无 tool_calls：`append_assistant_message`；`break`。
   - 对每个 tool：`tool.invocation` 子树 + SSE `tool_start`/`tool_result`；`append_tool_message`；把 tool 结果追加到内存 `messages`。
6. 完结 `agent_run`；yield `run_finished`。

SSE 行格式：`orjson.dumps({"v":1,"type":...,"run_id":...,"ts":...})` + `b"\n\n"`，外层加 `b"data: "` 前缀与 `b"\n\n"` 后缀（与现有 LLM SSE 一致）。

- [ ] **Step 2: 单测（mock `stream_chunks_messages`）**

在 `test_agent_run_service.py` 中 fake 两段流：第一段结束带 `tool_calls`，第二段纯文本；fake `repository` 为内存 list，断言节点类型序列包含 `llm.stream_segment` 与 `tool.execute`。

- [ ] **Step 3: Commit（可选）**

```bash
git add backend/app/agent/service/agent_run_service.py backend/tests/test_agent_run_service.py
git commit -m "feat(agent): run orchestration with SSE and node persistence"
```

---

## Task 9: FastAPI 路由

**Files:**

- Create: `backend/app/agent/api/schemas.py`
- Create: `backend/app/agent/api/router.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: `schemas.py`**

```python
class AgentSessionCreateIn(BaseModel):
    title: str | None = None
    agent_key: str | None = None


class AgentRunCreateIn(BaseModel):
    user_message: str = Field(min_length=1)
    provider_kind: ProviderKind = ProviderKind.openai_compatible
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    skill_ids: list[str] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
```

- [ ] **Step 2: `router.py`**

```python
router = APIRouter(prefix="/workspaces/{workspace_id}/agent", tags=["agent"])

@router.post("/sessions", response_model=AgentSessionOut)
async def create_agent_session(...):
    ...

@router.post("/sessions/{session_id}/runs")
async def create_run_sse(...):
    return StreamingResponse(service.run_stream_sse(...), media_type="text/event-stream")
```

`Depends(require_workspace_member)`、`Depends(get_current_user)` 与 `llm` 路由一致；`get_db` 注入 `AsyncSession`。**注意**：`StreamingResponse` 内异步生成器若持有 session，需在生成器内 **`async with` 会话边界** 或 **在路由层不关闭 session 直到流结束** — 采用项目惯用模式（参考其它 SSE 路由；若无先例，则在 `run_stream_sse` 内 `async for` 全程使用同一 `session`，路由 `finally` 关闭由 FastAPI 依赖处理：确保生成器消费完毕前不 dispose）。

- [ ] **Step 3: `core/api/router.py`**

```python
from app.agent.api.router import router as agent_router
api.include_router(agent_router)
```

- [ ] **Step 4: HTTP 测试 `tests/test_agent_api.py`**

无 token `POST /workspaces/{uuid}/agent/sessions` → 401。  
有 token但错误 `workspace_id` → 403。

Run: `pytest tests/test_agent_api.py -v`

- [ ] **Step 5: Commit（可选）**

```bash
git add backend/app/agent/api/schemas.py backend/app/agent/api/router.py backend/app/core/api/router.py backend/tests/test_agent_api.py
git commit -m "feat(agent): workspace-scoped sessions and SSE run endpoint"
```

---

## Task 10: 技能包占位与文档

**Files:**

- Create: `backend/app/agent/skills/INDEX.md`
- Create: `backend/app/agent/skills/example_echo/SKILL.md`
- Create: `backend/app/agent/skills/example_echo/tools.py`（若采用「仅测试注册 tool」则 skills 下只放 `SKILL.md`，`tools.py` 省略）

`INDEX.md` 示例内容（Markdown）：

```markdown
# Agent Skills Index

Sub-skills:

- example_echo
```

- [ ] **Step 1: Commit（可选）**

```bash
git add backend/app/agent/skills/INDEX.md backend/app/agent/skills/example_echo
git commit -m "docs(agent): add skills INDEX and example skill pack"
```

---

## Self-review（对照 spec）

| Spec 章节 | 覆盖 Task |
|-----------|-----------|
| 方案 3 + `llm` 扩展 tools/流式 | Task 2–3 |
| 真 SSE + envelope | Task 8–9 |
| 四张表 + 跨请求 message | Task 4–5, 8 |
| 细粒度节点树 + 分段策略 | Task 1, 7–8 |
| `INDEX.md` 固定 | Task 6, 10 |
| 脱敏与大小上限 | Task 6, 8 |
| 安全：api_key 不入库 | Task 8（落库前 `redact_json`） |
| 回归 `llm` 不传 tools | Task 2–3 的 `test_llm.py` |

**占位符扫描：** 本计划未使用 “TBD / 稍后实现”；`AgentSessionOut` 等响应模型在 Task 9 需补全字段（`id`, `created_at`）— 实现时于同 Task 写出完整 Pydantic 类。

**类型一致性：** `ProviderKind` 一律从 `app.llm.domain.models` 导入；`messages` 全链路 `list[dict[str, Any]]`。

---

## 执行交接

**计划已保存到** `docs/superpowers/plans/2026-05-15-agent-llm-tools-sse-persistence.md`。

**两种执行方式（二选一）：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理执行，任务间人工/代理复核。需使用 **`superpowers:subagent-driven-development`**。
2. **Inline Execution** — 本会话内按 Task 顺序实现，使用 **`superpowers:executing-plans`** 做批次与检查点。

你想用哪一种？若无需形式化 skill，直接回复「在本会话按 Task 1 开始实现」即可。
