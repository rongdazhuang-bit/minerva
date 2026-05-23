# LLM OpenAI-Compatible Runtime Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify `backend/app/llm` so all runtime model calls use one OpenAI-compatible strategy while keeping legacy `provider_kind` values compatible and verifying `backend/app/agent` remains independent.

**Architecture:** `OpenAICompatibleStrategy` becomes the only runtime strategy. `get_strategy()` accepts legacy provider values but returns the same singleton, while `ChatService` defaults to that strategy and no longer requires business callers to pass `provider_kind`. Agent continues to use `ChatModelFactory -> langchain_openai.ChatOpenAI` and is covered by regression tests and docs.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, direct `httpx` calls, LangChain OpenAI, pytest.

---

## File Structure

- Modify: `backend/pyproject.toml`  
  Add `pytest` to dev dependencies if the repository still lacks a test runner dependency.
- Create: `backend/tests/test_llm_strategy_unification.py`  
  Unit tests for `get_strategy()`, URL normalization, and `ChatService` default strategy selection.
- Create: `backend/tests/test_agent_chat_model_factory.py`  
  Regression tests proving Agent model construction does not depend on `app/llm` strategy registration.
- Modify: `backend/app/llm/strategies/openai_compatible.py`  
  Add shared `normalize_openai_base_url()` and use it in `complete()` and `stream()`.
- Modify: `backend/app/llm/strategies/__init__.py`  
  Remove vendor strategy imports and map all compatible legacy values to the same singleton.
- Delete: `backend/app/llm/strategies/volcengine_compatible.py`
- Delete: `backend/app/llm/strategies/aliyun_compatible.py`
- Modify: `backend/app/llm/service/chat_service.py`  
  Make `provider_kind` optional for compatibility and default it to `ProviderKind.openai`; remove mandatory internal usage.
- Modify: `backend/app/llm/api/router.py`  
  Continue passing HTTP `provider_kind` for compatibility.
- Modify: `backend/app/rule/service/rule_base_service.py`  
  Remove `ProviderKind.openai` hardcoding from internal `ChatService` calls.
- Modify: `backend/app/translate/service/translate_llm.py`  
  Remove `ProviderKind.openai` hardcoding from internal `ChatService` calls.
- Modify: `docs/ai-api.md`
- Modify: `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`
- Modify: `docs/superpowers/specs/2026-05-17-volcengine-compatible-llm-design.md`
- Modify: `docs/agent-module-design.md`
- Modify: `docs/superpowers/specs/2026-05-23-llm-openai-compatible-runtime-unification-design.md`  
  Mark implementation status and add implementation mapping after code changes.

---

### Task 1: Establish LLM Strategy Tests

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/test_llm_strategy_unification.py`

- [ ] **Step 1: Add pytest to backend dev dependencies if absent**

In `backend/pyproject.toml`, update the dev optional dependencies:

```toml
[project.optional-dependencies]
dev = [
  "httpx>=0.28",
  "pytest>=8",
  "ruff>=0.8",
]
```

- [ ] **Step 2: Create failing strategy unification tests**

Create `backend/tests/test_llm_strategy_unification.py`:

```python
"""Tests for unified OpenAI-compatible LLM runtime strategy."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.exceptions import AppError
from app.llm.domain.models import ChatCallParams, ProviderKind
from app.llm.service.chat_service import ChatService
from app.llm.strategies import get_strategy
from app.llm.strategies.openai_compatible import (
    OpenAICompatibleStrategy,
    normalize_openai_base_url,
)


def test_legacy_provider_kinds_resolve_to_same_strategy() -> None:
    """All supported legacy provider values should use one runtime strategy."""

    openai_strategy = get_strategy(ProviderKind.openai)

    assert isinstance(openai_strategy, OpenAICompatibleStrategy)
    assert get_strategy(ProviderKind.volcengine) is openai_strategy
    assert get_strategy(ProviderKind.aliyun) is openai_strategy
    assert get_strategy("openai") is openai_strategy
    assert get_strategy("volcengine") is openai_strategy
    assert get_strategy("aliyun") is openai_strategy


def test_unknown_provider_kind_still_fails() -> None:
    """Unsupported provider values must not silently call an upstream model."""

    with pytest.raises(AppError) as exc:
        get_strategy("unknown")

    assert exc.value.code == "ai.provider.unknown"
    assert exc.value.status_code == 400


def test_normalize_openai_base_url_trims_slashes() -> None:
    """Ordinary OpenAI-compatible roots only need trailing slash cleanup."""

    assert normalize_openai_base_url("https://example.com/v1///") == "https://example.com/v1"


def test_normalize_openai_base_url_keeps_full_configured_url() -> None:
    """The database URL is already complete and must not be rewritten."""

    assert (
        normalize_openai_base_url("https://ark.cn-beijing.volces.com/api/v3/responses/")
        == "https://ark.cn-beijing.volces.com/api/v3/responses"
    )


class _RecordingStrategy:
    """Minimal strategy used to verify ChatService parameter assembly."""

    def __init__(self) -> None:
        self.params: ChatCallParams | None = None

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Record non-streaming parameters and return a fake completion."""

        self.params = params
        return {"id": "chatcmpl-test", "choices": []}

    async def stream(self, params: ChatCallParams):
        """Yield one fake chunk for stream tests."""

        self.params = params
        yield {"choices": [{"delta": {"content": "ok"}}]}


def test_chat_service_complete_defaults_to_openai_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Internal callers should not need to pass provider_kind."""

    recording = _RecordingStrategy()
    monkeypatch.setattr("app.llm.service.chat_service.get_strategy", lambda provider_kind=ProviderKind.openai: recording)

    result = asyncio.run(
        ChatService().complete(
            base_url="https://example.com/v1/chat/completions",
            api_key="key",
            model="model-a",
            user_prompt="hello",
        )
    )

    assert result["id"] == "chatcmpl-test"
    assert recording.params is not None
    assert recording.params.model == "model-a"
    assert recording.params.messages == [{"role": "user", "content": "hello"}]
```

- [ ] **Step 3: Run the new tests and confirm they fail for expected reasons**

Run:

```bash
cd backend
python -m pytest tests/test_llm_strategy_unification.py -q
```

Expected before implementation:

```text
FAILED ... cannot import name 'normalize_openai_base_url'
FAILED ... get_strategy(ProviderKind.volcengine) is not openai_strategy
FAILED ... ChatService.complete() missing required keyword-only argument: 'provider_kind'
```

---

### Task 2: Unify Strategy Registry and URL Normalization

**Files:**
- Modify: `backend/app/llm/strategies/openai_compatible.py`
- Modify: `backend/app/llm/strategies/__init__.py`
- Delete: `backend/app/llm/strategies/volcengine_compatible.py`
- Delete: `backend/app/llm/strategies/aliyun_compatible.py`
- Test: `backend/tests/test_llm_strategy_unification.py`

- [ ] **Step 1: Add shared base URL normalization**

In `backend/app/llm/strategies/openai_compatible.py`, add this helper near `_chat_completions_url()`:

```python
def normalize_openai_base_url(base_url: str) -> str:
    """Normalize the configured OpenAI-compatible request URL without path rewriting."""

    return base_url.rstrip("/")
```

- [ ] **Step 2: Use the helper in non-streaming calls**

Change `complete()` from:

```python
base_url = params.base_url.rstrip("/")
```

to:

```python
base_url = normalize_openai_base_url(params.base_url)
```

- [ ] **Step 3: Use the helper in streaming calls**

Change `stream()` from:

```python
base_url = params.base_url.rstrip("/")
```

to:

```python
base_url = normalize_openai_base_url(params.base_url)
```

- [ ] **Step 4: Replace the strategy registry**

Replace `backend/app/llm/strategies/__init__.py` with:

```python
"""Register the unified OpenAI-compatible chat completion strategy."""

from app.llm.domain.models import ProviderKind
from app.llm.strategies.base import ChatCompletionStrategy
from app.llm.strategies.openai_compatible import OpenAICompatibleStrategy
from app.exceptions import AppError

__all__ = [
    "ChatCompletionStrategy",
    "OpenAICompatibleStrategy",
    "get_strategy",
]

_OPENAI_COMPATIBLE_STRATEGY = OpenAICompatibleStrategy()
_COMPATIBLE_PROVIDER_KINDS = frozenset(
    {
        ProviderKind.openai.value,
        ProviderKind.volcengine.value,
        ProviderKind.aliyun.value,
    }
)


def get_strategy(provider_kind: ProviderKind | str = ProviderKind.openai) -> ChatCompletionStrategy:
    """Return the unified strategy for supported legacy provider values."""

    key = provider_kind.value if isinstance(provider_kind, ProviderKind) else provider_kind
    if key not in _COMPATIBLE_PROVIDER_KINDS:
        raise AppError(
            "ai.provider.unknown",
            f"Unknown provider_kind: {provider_kind!s}.",
            400,
        )
    return _OPENAI_COMPATIBLE_STRATEGY
```

- [ ] **Step 5: Delete obsolete strategy files**

Delete:

```text
backend/app/llm/strategies/volcengine_compatible.py
backend/app/llm/strategies/aliyun_compatible.py
```

- [ ] **Step 6: Run strategy tests**

Run:

```bash
cd backend
python -m pytest tests/test_llm_strategy_unification.py::test_legacy_provider_kinds_resolve_to_same_strategy tests/test_llm_strategy_unification.py::test_unknown_provider_kind_still_fails tests/test_llm_strategy_unification.py::test_normalize_openai_base_url_trims_slashes tests/test_llm_strategy_unification.py::test_normalize_openai_base_url_removes_responses_suffix -q
```

Expected:

```text
4 passed
```

- [ ] **Step 7: Search for deleted strategy references**

Run:

```bash
python - <<'PY'
from pathlib import Path
needles = ("VolcengineCompatibleStrategy", "AliyunCompatibleStrategy", "volcengine_compatible", "aliyun_compatible")
hits = []
for path in Path(".").rglob("*"):
    if path.is_file() and path.suffix in {".py", ".md"} and ".venv" not in path.parts:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            if needle in text:
                hits.append((str(path), needle))
if hits:
    for hit in hits:
        print(hit)
    raise SystemExit(1)
PY
```

Expected after code cleanup but before docs cleanup: hits may remain in docs only. Python code should have no hits.

---

### Task 3: Make ChatService Provider Kind Optional

**Files:**
- Modify: `backend/app/llm/service/chat_service.py`
- Modify: `backend/app/llm/api/router.py`
- Modify: `backend/app/rule/service/rule_base_service.py`
- Modify: `backend/app/translate/service/translate_llm.py`
- Test: `backend/tests/test_llm_strategy_unification.py`

- [ ] **Step 1: Update imports**

Keep `ProviderKind` imported in `chat_service.py`, because it remains the compatibility default:

```python
from app.llm.domain.models import ChatCallParams, ChatMessage, ProviderKind
```

- [ ] **Step 2: Make provider_kind optional in `complete()`**

Change the signature in `ChatService.complete()` to:

```python
async def complete(
    self,
    *,
    base_url: str,
    api_key: str,
    model: str,
    provider_kind: ProviderKind | str = ProviderKind.openai,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    messages: list[ChatMessage] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform non-streaming completion via the unified OpenAI-compatible strategy."""
```

Leave `strategy = get_strategy(provider_kind)` in place so HTTP callers still validate old values.

- [ ] **Step 3: Make provider_kind optional in `complete_messages()`**

Use this signature:

```python
async def complete_messages(
    self,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    provider_kind: ProviderKind | str = ProviderKind.openai,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Non-streaming completion using caller-built OpenAI-style messages."""
```

- [ ] **Step 4: Make provider_kind optional in `stream_chunks()`**

Use this signature:

```python
async def stream_chunks(
    self,
    *,
    base_url: str,
    api_key: str,
    model: str,
    provider_kind: ProviderKind | str = ProviderKind.openai,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    messages: list[ChatMessage] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield upstream chunks from the unified OpenAI-compatible strategy."""
```

- [ ] **Step 5: Make provider_kind optional in `stream_chunks_messages()`**

Use this signature:

```python
async def stream_chunks_messages(
    self,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    provider_kind: ProviderKind | str = ProviderKind.openai,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream completion chunks using caller-built OpenAI-style messages."""
```

- [ ] **Step 6: Make provider_kind optional in `stream_sse_lines()`**

Use this signature:

```python
async def stream_sse_lines(
    self,
    *,
    base_url: str,
    api_key: str,
    model: str,
    provider_kind: ProviderKind | str = ProviderKind.openai,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    messages: list[ChatMessage] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> AsyncIterator[bytes]:
    """Emit SSE-formatted data lines ending with [DONE]."""
```

- [ ] **Step 7: Keep HTTP compatibility in router**

Leave `backend/app/llm/api/router.py` passing:

```python
provider_kind=body.provider_kind,
```

This preserves explicit HTTP validation of legacy `provider_kind` values.

- [ ] **Step 8: Remove internal hardcoded ProviderKind from translate**

In `backend/app/translate/service/translate_llm.py`, remove `ProviderKind` from the import:

```python
from app.llm.domain.models import ChatMessage
```

Then remove this keyword from the `chat_service.complete(...)` call:

```python
provider_kind=ProviderKind.openai,
```

- [ ] **Step 9: Remove internal hardcoded ProviderKind from rule**

In `backend/app/rule/service/rule_base_service.py`, remove `ProviderKind` from the import:

```python
from app.llm.domain.models import ChatMessage
```

Then remove this keyword from the `chat_service.complete(...)` call:

```python
provider_kind=ProviderKind.openai,
```

- [ ] **Step 10: Run ChatService default test**

Run:

```bash
cd backend
python -m pytest tests/test_llm_strategy_unification.py::test_chat_service_complete_defaults_to_openai_strategy -q
```

Expected:

```text
1 passed
```

---

### Task 4: Add Agent Regression Tests

**Files:**
- Create: `backend/tests/test_agent_chat_model_factory.py`
- Test: `backend/app/agent/infrastructure/chat_model_factory.py`

- [ ] **Step 1: Create Agent factory tests**

Create `backend/tests/test_agent_chat_model_factory.py`:

```python
"""Regression tests for Agent ChatModelFactory independence from app.llm strategies."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.exceptions import AppError


def _model_row(**overrides):
    """Build the minimal SysModel-like row needed by ChatModelFactory."""

    workspace_id = overrides.pop("workspace_id", uuid.uuid4())
    values = {
        "workspace_id": workspace_id,
        "enabled": True,
        "endpoint_url": "https://example.com/v1/",
        "api_key": "secret",
        "model_name": "gpt-compatible",
        "max_tokens_to_sample": 512,
    }
    values.update(overrides)
    return SimpleNamespace(**values), workspace_id


def test_agent_chat_model_factory_constructs_chat_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent should keep using LangChain ChatOpenAI with SysModel connection data."""

    captured: dict = {}

    class FakeChatOpenAI:
        """Capture constructor kwargs without contacting an upstream model."""

        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.ChatOpenAI", FakeChatOpenAI)

    row, workspace_id = _model_row()
    model = ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert isinstance(model, FakeChatOpenAI)
    assert captured == {
        "model": "gpt-compatible",
        "base_url": "https://example.com/v1",
        "api_key": "secret",
        "max_tokens": 512,
    }


def test_agent_chat_model_factory_rejects_wrong_workspace() -> None:
    """Workspace ownership remains validated independently of LLM strategies."""

    row, _workspace_id = _model_row()

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=uuid.uuid4())

    assert exc.value.code == "agent.model_not_found"


def test_agent_chat_model_factory_rejects_missing_endpoint() -> None:
    """Agent model rows still require an OpenAI-compatible endpoint URL."""

    row, workspace_id = _model_row(endpoint_url="")

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_misconfigured"


def test_agent_chat_model_factory_rejects_missing_api_key() -> None:
    """Agent model rows still require an API key for ChatOpenAI construction."""

    row, workspace_id = _model_row(api_key="")

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_misconfigured"
```

- [ ] **Step 2: Run Agent factory tests**

Run:

```bash
cd backend
python -m pytest tests/test_agent_chat_model_factory.py -q
```

Expected:

```text
4 passed
```

---

### Task 5: Update Documentation

**Files:**
- Modify: `docs/ai-api.md`
- Modify: `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`
- Modify: `docs/superpowers/specs/2026-05-17-volcengine-compatible-llm-design.md`
- Modify: `docs/agent-module-design.md`
- Modify: `docs/superpowers/specs/2026-05-23-llm-openai-compatible-runtime-unification-design.md`

- [ ] **Step 1: Update `docs/ai-api.md` module structure**

Change:

```markdown
- `app.llm.strategies`：`openai`（默认）、`volcengine_compatible`（火山 Ark OpenAI 兼容）、`aliyun_compatible`（阿里云 OpenAI 兼容，未实现）。
```

to:

```markdown
- `app.llm.strategies`：单一 `OpenAICompatibleStrategy`。`provider_kind=openai|volcengine|aliyun` 仅作为兼容输入值，运行时均走 OpenAI Chat Completions 兼容协议。
```

- [ ] **Step 2: Update `docs/ai-api.md` code examples**

Change the import:

```python
from app.llm import ProviderKind, chat_service
```

to:

```python
from app.llm import chat_service
```

Remove `provider_kind=ProviderKind.openai,` from all internal code examples.

- [ ] **Step 3: Replace Volcengine and placeholder sections**

Replace the `Volcengine Ark` and `占位策略` sections with:

```markdown
## 兼容 provider_kind

HTTP 请求体仍接受 `provider_kind=openai|volcengine|aliyun`，用于兼容历史调用和 OpenAPI 文档。运行时不会按该字段选择不同供应商策略，三者都会进入 `OpenAICompatibleStrategy`。

火山 Ark、阿里云或其它模型服务只要提供 OpenAI Chat Completions 兼容 endpoint，就通过完整 `base_url`、`api_key`、`model` 接入。后端不再拼接或改写路径；配置什么 URL 就请求什么 URL。

## Agent v2

Agent v2 不调用 `app.llm.ChatService` 或 `/llm/chat/completions`，而是通过 `model_id` 读取 `sys_models` 并由 `ChatModelFactory` 构造 `langchain_openai.ChatOpenAI`。本模块的 `provider_kind` 兼容入口不影响 Agent 主链路。
```

- [ ] **Step 4: Update the 2026-04-28 AI API spec status and implementation mapping**

In `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`, update the status line to mention runtime unification:

```markdown
**状态**：已实现（2026-05-18 按代码回填；2026-05-23 运行时策略统一为单一 OpenAI 兼容策略；`sys_models` 解析未做）
```

In the implementation mapping table, change:

```markdown
| 策略 | `openai`（实现）、`volcengine`（实现）、`aliyun_compatible`（501 未实现） |
```

to:

```markdown
| 策略 | 单一 `OpenAICompatibleStrategy`；`provider_kind=openai|volcengine|aliyun` 为兼容输入值 |
```

- [ ] **Step 5: Mark the Volcengine strategy spec as superseded**

In `docs/superpowers/specs/2026-05-17-volcengine-compatible-llm-design.md`, update status:

```markdown
**状态**：已实现，2026-05-23 被统一 OpenAI 兼容运行时策略取代；本文保留为历史实现记录
```

Add near the top:

```markdown
> 2026-05-23 更新：独立 `VolcengineCompatibleStrategy` 已不再作为运行时策略存在。`provider_kind=volcengine` 仍可作为兼容输入，但实际调用进入 `OpenAICompatibleStrategy`。
```

- [ ] **Step 6: Update Agent module docs**

In `docs/agent-module-design.md`, add this paragraph after the tech stack list:

```markdown
### 1.3.1 与 `app/llm` 策略统一的关系

Agent v2 不调用 `app.llm.ChatService` 或 `get_strategy()`，也不依赖 `provider_kind` 选择供应商策略。它通过 `model_id` 读取 `sys_models`，再由 `ChatModelFactory` 构造 `langchain_openai.ChatOpenAI`。因此 `app/llm` 在 2026-05-23 统一为单一 OpenAI 兼容策略后，Agent 主链路无需改造；回归验证重点是 `ChatModelFactory` 仍能按 `endpoint_url`、`api_key`、`model_name` 构造客户端。
```

- [ ] **Step 7: Update the new unification spec implementation status**

In `docs/superpowers/specs/2026-05-23-llm-openai-compatible-runtime-unification-design.md`, update:

```markdown
**状态**：已实现（2026-05-23）
```

Add an implementation mapping section before the self-review:

```markdown
## 12. 实现对照（以代码为准，2026-05-23）

| 项 | 当前代码位置 |
|----|--------------|
| 统一策略 | `backend/app/llm/strategies/openai_compatible.py` |
| 兼容入口 | `backend/app/llm/strategies/__init__.py` |
| 内部服务默认策略 | `backend/app/llm/service/chat_service.py` |
| HTTP 兼容字段 | `backend/app/llm/api/schemas.py`、`backend/app/llm/api/router.py` |
| Agent 独立链路 | `backend/app/agent/infrastructure/chat_model_factory.py` |
| 回归测试 | `backend/tests/test_llm_strategy_unification.py`、`backend/tests/test_agent_chat_model_factory.py` |
```

Then renumber the old self-review heading to `## 13. 规格自检（2026-05-23）`.

---

### Task 6: Final Verification and Cleanup

**Files:**
- Check: `backend/app/llm/`
- Check: `backend/app/agent/`
- Check: `backend/tests/`
- Check: `docs/`

- [ ] **Step 1: Run all new tests**

Run:

```bash
cd backend
python -m pytest tests/test_llm_strategy_unification.py tests/test_agent_chat_model_factory.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 2: Run linter on touched backend code**

Run:

```bash
cd backend
python -m ruff check app/llm app/translate app/rule app/agent tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Verify obsolete Python references are gone**

Run:

```bash
cd backend
python - <<'PY'
from pathlib import Path
needles = ("VolcengineCompatibleStrategy", "AliyunCompatibleStrategy", "volcengine_compatible", "aliyun_compatible")
for path in Path("app").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: still contains {needle}")
print("No obsolete strategy references in backend/app")
PY
```

Expected:

```text
No obsolete strategy references in backend/app
```

- [ ] **Step 4: Verify internal ProviderKind hardcoding is removed**

Run:

```bash
cd backend
python - <<'PY'
from pathlib import Path
hits = []
for path in Path("app").rglob("*.py"):
    if "app/llm" in path.as_posix():
        continue
    text = path.read_text(encoding="utf-8")
    if "ProviderKind.openai" in text or "provider_kind=ProviderKind.openai" in text:
        hits.append(str(path))
if hits:
    raise SystemExit("\\n".join(hits))
print("No internal ProviderKind.openai hardcoding outside app/llm")
PY
```

Expected:

```text
No internal ProviderKind.openai hardcoding outside app/llm
```

- [ ] **Step 5: Check IDE lints for edited files**

Use Cursor lints for:

```text
backend/app/llm/strategies/openai_compatible.py
backend/app/llm/strategies/__init__.py
backend/app/llm/service/chat_service.py
backend/app/rule/service/rule_base_service.py
backend/app/translate/service/translate_llm.py
backend/app/agent/infrastructure/chat_model_factory.py
backend/tests/test_llm_strategy_unification.py
backend/tests/test_agent_chat_model_factory.py
```

Expected: no newly introduced diagnostics.

---

## Self-Review

- Spec coverage: The plan covers unified strategy, soft-compatible legacy `provider_kind`, internal `ChatService` cleanup, deletion of obsolete strategy files, dependency review, Agent impact verification, docs, and final checks.
- Placeholder scan: No red-flag placeholder terms or unspecified “add tests” steps remain; each task names exact files, snippets, commands, and expected outcomes.
- Type consistency: `ProviderKind | str = ProviderKind.openai` is used consistently for compatibility; `normalize_openai_base_url()` is defined before tests import it; Agent tests monkeypatch `ChatOpenAI` at the exact factory import path.
