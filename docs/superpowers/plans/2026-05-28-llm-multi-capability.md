# LLM 多能力与 model_id 中心化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 `backend/app/llm`，以 `model_id` 为中心支持 Chat（text/translate）、Embedding、Rerank 三类能力，封装入参/出参实体并按 `model_type` 选策略；HTTP 分端点强校验；迁移 rule/translate 调用方并删除 `ChatService`。

**Architecture:** `ModelResolver` 从 `sys_models` 解析 `ResolvedModel`；`LlmService` 门面按能力调用 `TextChatStrategy` / `EmbeddingStrategy` / `RerankStrategy`；策略通过 `http_common.py` 共用 httpx 与错误映射；上游 URL 直接使用 `endpoint_url`（仅 `rstrip("/")`）。

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx, SQLAlchemy async, pytest.

**Design spec:** `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`

---

## File Structure

| 操作 | 路径 | 职责 |
|------|------|------|
| Create | `backend/app/llm/domain/resolved_model.py` | `ResolvedModel` |
| Modify | `backend/app/llm/domain/models.py` | 各能力 CallParams / Result；保留 `ChatMessage` |
| Modify | `backend/app/llm/domain/__init__.py` | 导出新类型 |
| Create | `backend/app/llm/strategies/http_common.py` | 共用 httpx、错误映射、`normalize_endpoint_url` |
| Modify | `backend/app/llm/strategies/base.py` | 三类策略 Protocol |
| Create | `backend/app/llm/strategies/text_chat.py` | text + translate Chat 策略 |
| Create | `backend/app/llm/strategies/embedding.py` | Embedding 策略 |
| Create | `backend/app/llm/strategies/rerank.py` | Rerank 策略 |
| Modify | `backend/app/llm/strategies/__init__.py` | `get_text_chat_strategy` 等 |
| Delete | `backend/app/llm/strategies/openai_compatible.py` | 逻辑迁入 text_chat + http_common |
| Create | `backend/app/llm/service/model_resolver.py` | `resolve_model` |
| Create | `backend/app/llm/service/llm_service.py` | `LlmService` + `llm_service` 单例 |
| Delete | `backend/app/llm/service/chat_service.py` | 由 llm_service 替代 |
| Modify | `backend/app/llm/service/__init__.py` | 导出 `llm_service` |
| Modify | `backend/app/llm/api/schemas.py` | model_id 请求体 |
| Modify | `backend/app/llm/api/router.py` | 三端点 + DB session |
| Modify | `backend/app/llm/__init__.py` | 导出新 public API |
| Modify | `backend/app/rule/service/rule_base_service.py` | 改用 `llm_service` |
| Modify | `backend/app/translate/service/translate_llm.py` | 改用 `llm_service` |
| Modify | `backend/app/agent/infrastructure/chat_model_factory.py` | import 路径更新 |
| Modify | `backend/app/agent/infrastructure/direct_endpoint_openai_client.py` | import 路径更新 |
| Rewrite | `backend/tests/test_llm_strategy_unification.py` | 新架构测试 |
| Create | `backend/tests/test_llm_model_resolver.py` | resolver 测试 |
| Create | `backend/tests/test_llm_multi_capability.py` | embedding/rerank 策略测试 |
| Modify | `docs/ai-api.md` | 新 API 与调用方式 |
| Modify | `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md` | 标记已实现 |

---

### Task 1: Domain 实体与常量

**Files:**
- Create: `backend/app/llm/domain/resolved_model.py`
- Modify: `backend/app/llm/domain/models.py`
- Modify: `backend/app/llm/domain/__init__.py`
- Test: `backend/tests/test_llm_domain_models.py`

- [ ] **Step 1: Write failing domain tests**

Create `backend/tests/test_llm_domain_models.py`:

```python
"""Tests for LLM domain DTOs."""

from __future__ import annotations

from uuid import uuid4

from app.llm.domain.models import (
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TYPES,
    EMBEDDING_MODEL_TYPES,
    RERANK_MODEL_TYPES,
    ResolvedModel,
)


def test_text_chat_result_assistant_text() -> None:
    """TextChatResult extracts assistant content from OpenAI-shaped payload."""

    result = TextChatResult(
        choices=[{"message": {"role": "assistant", "content": "hello"}}],
        raw={"choices": [{"message": {"content": "hello"}}]},
    )
    assert result.assistant_text() == "hello"


def test_text_chat_result_empty_choices() -> None:
    """Missing choices yield empty assistant text."""

    result = TextChatResult(choices=[], raw={})
    assert result.assistant_text() == ""


def test_model_type_constants() -> None:
    """Allowed model_type sets match spec."""

    assert CHAT_MODEL_TYPES == frozenset({"text", "translate"})
    assert EMBEDDING_MODEL_TYPES == frozenset({"embedding"})
    assert RERANK_MODEL_TYPES == frozenset({"rerank"})


def test_resolved_model_fields() -> None:
    """ResolvedModel carries upstream credentials."""

    mid = uuid4()
    row = ResolvedModel(
        model_id=mid,
        model_name="gpt-4o-mini",
        model_type="text",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="secret",
    )
    assert row.model_id == mid
    assert row.model_name == "gpt-4o-mini"


def test_embedding_and_rerank_params() -> None:
    """Embedding and rerank params accept spec fields."""

    emb = EmbeddingCallParams(input="hello", dimensions=1536)
    assert emb.encoding_format == "float"
    rerank = RerankCallParams(query="q", documents=["a", "b"], top_n=2)
    assert rerank.top_n == 2
    assert EmbeddingResult(data=[], raw={}).data == []
    assert RerankResult(results=[], raw={}).results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_domain_models.py -v`

Expected: FAIL — `ImportError` for missing modules/classes.

- [ ] **Step 3: Implement domain models**

Create `backend/app/llm/domain/resolved_model.py`:

```python
"""Resolved upstream model credentials loaded from ``sys_models``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

CHAT_MODEL_TYPES = frozenset({"text", "translate"})
EMBEDDING_MODEL_TYPES = frozenset({"embedding"})
RERANK_MODEL_TYPES = frozenset({"rerank"})


class ResolvedModel(BaseModel):
    """Workspace-scoped model row normalized for strategy invocation."""

    model_id: UUID
    model_name: str = Field(description="Upstream model field sent to the provider.")
    model_type: str
    endpoint_url: str = Field(description="Full provider URL; used as POST target.")
    api_key: str
```

Replace `backend/app/llm/domain/models.py` content (keep `ChatMessage`; remove `ProviderKind` and `ChatCallParams`):

```python
"""Domain primitives shared between AI strategies and HTTP schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single chat message; content aligns with OpenAI chat message text content."""

    role: str
    content: str


class TextChatCallParams(BaseModel):
    """OpenAI Chat Completions call parameters (text and translate models)."""

    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    n: int | None = None
    stop: list[str] | str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class TextChatResult(BaseModel):
    """Parsed OpenAI Chat Completions response."""

    id: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    choices: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def assistant_text(self) -> str:
        """Extract assistant text from the first choice, if present."""

        if not self.choices:
            return ""
        message = self.choices[0].get("message") or {}
        content = message.get("content")
        return (content or "").strip() if isinstance(content, str) else ""


class EmbeddingCallParams(BaseModel):
    """OpenAI Embeddings API call parameters."""

    input: str | list[str]
    dimensions: int | None = None
    encoding_format: str = "float"


class EmbeddingResult(BaseModel):
    """Parsed OpenAI Embeddings response."""

    data: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RerankCallParams(BaseModel):
    """OpenAI-compatible rerank call parameters."""

    query: str
    documents: list[str] = Field(min_length=1)
    top_n: int | None = Field(default=None, ge=1)


class RerankResult(BaseModel):
    """Parsed OpenAI-compatible rerank response."""

    id: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
```

Update `backend/app/llm/domain/__init__.py`:

```python
"""LLM domain exports."""

from app.llm.domain.models import (
    ChatMessage,
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TYPES,
    EMBEDDING_MODEL_TYPES,
    RERANK_MODEL_TYPES,
    ResolvedModel,
)

__all__ = [
    "CHAT_MODEL_TYPES",
    "EMBEDDING_MODEL_TYPES",
    "RERANK_MODEL_TYPES",
    "ChatMessage",
    "EmbeddingCallParams",
    "EmbeddingResult",
    "RerankCallParams",
    "RerankResult",
    "ResolvedModel",
    "TextChatCallParams",
    "TextChatResult",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_domain_models.py -v`

Expected: PASS (4–5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/domain backend/tests/test_llm_domain_models.py
git commit -m "feat(llm): add multi-capability domain DTOs and ResolvedModel"
```

---

### Task 2: HTTP 公共基础设施（http_common）

**Files:**
- Create: `backend/app/llm/strategies/http_common.py`
- Test: `backend/tests/test_llm_http_common.py`

- [ ] **Step 1: Write failing http_common tests**

Create `backend/tests/test_llm_http_common.py`:

```python
"""Tests for shared LLM HTTP helpers."""

from __future__ import annotations

import pytest
from httpx import HTTPStatusError, Request, Response

from app.exceptions import AppError
from app.llm.strategies.http_common import (
    map_upstream_error,
    normalize_endpoint_url,
    request_headers,
)


def test_normalize_endpoint_url_trims_slashes() -> None:
    """Configured URLs only need trailing slash cleanup."""

    assert (
        normalize_endpoint_url("https://example.com/v1/chat/completions///")
        == "https://example.com/v1/chat/completions"
    )


def test_request_headers_bearer() -> None:
    """Authorization uses Bearer scheme."""

    headers = request_headers("key-abc")
    assert headers["Authorization"] == "Bearer key-abc"
    assert headers["Content-Type"] == "application/json"


def test_map_upstream_error_unauthorized() -> None:
    """HTTP 401 maps to ai.upstream.unauthorized."""

    req = Request("POST", "https://example.com")
    resp = Response(401, request=req)
    err = HTTPStatusError("401", request=req, response=resp)
    mapped = map_upstream_error(err)
    assert isinstance(mapped, AppError)
    assert mapped.code == "ai.upstream.unauthorized"
    assert mapped.status_code == 502
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_http_common.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement http_common**

Create `backend/app/llm/strategies/http_common.py` by extracting from `openai_compatible.py`:

```python
"""Shared httpx helpers, logging, and upstream error mapping for LLM strategies."""

from __future__ import annotations

import logging
from typing import Any

import orjson
from httpx import AsyncClient, HTTPStatusError, RequestError, Timeout, TimeoutException

from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)

_LOG_JSON_MAX_CHARS = 100_000


def normalize_endpoint_url(url: str) -> str:
    """Normalize configured provider URL without path rewriting."""

    return url.rstrip("/")


# Backward-compatible alias for agent imports during migration.
normalize_openai_base_url = normalize_endpoint_url


def json_for_log(data: Any) -> str:
    """Serialize for logging; truncate very large payloads."""

    raw = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode()
    if len(raw) > _LOG_JSON_MAX_CHARS:
        return raw[:_LOG_JSON_MAX_CHARS] + f"... [truncated, original_length={len(raw)} chars]"
    return raw


def text_for_log(text: str) -> str:
    """Truncate huge plaintext log payloads."""

    if len(text) > _LOG_JSON_MAX_CHARS:
        return text[:_LOG_JSON_MAX_CHARS] + f"... [truncated, original_length={len(text)}]"
    return text


def request_headers(api_key: str) -> dict[str, str]:
    """Build OpenAI-compatible HTTP headers."""

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def client_timeout() -> Timeout:
    """Construct httpx.Timeout from AI-related settings."""

    return Timeout(
        connect=settings.ai_http_connect_timeout,
        read=settings.ai_http_read_timeout,
        write=settings.ai_http_read_timeout,
        pool=settings.ai_http_connect_timeout,
    )


def log_upstream_http_error(*, url: str, exc: HTTPStatusError, method: str) -> None:
    """Emit WARNING logs containing sanitized upstream HTTP bodies."""

    body = ""
    if exc.response is not None:
        try:
            body = exc.response.text
        except Exception:  # noqa: BLE001
            body = repr(exc)
    log.warning(
        "ai upstream error method=%s url=%s status=%s response=%s",
        method,
        url,
        exc.response.status_code if exc.response is not None else "unknown",
        text_for_log(body) if body else "",
    )


def map_upstream_error(exc: BaseException) -> AppError:
    """Normalize upstream transport failures into stable AppError codes."""

    if isinstance(exc, HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return AppError("ai.upstream.unauthorized", "Upstream rejected the API key.", 502)
        if code == 429:
            return AppError("ai.upstream.rate_limited", "Upstream rate limited the request.", 429)
        if code == 503:
            return AppError("ai.upstream.unavailable", "Upstream temporarily unavailable.", 503)
        if code >= 500:
            return AppError("ai.upstream.error", f"Upstream returned HTTP {code}.", 502)
        return AppError("ai.upstream.bad_request", f"Upstream returned HTTP {code}.", 400)
    if isinstance(exc, TimeoutException):
        return AppError("ai.upstream.timeout", "Upstream request timed out.", 504)
    if isinstance(exc, RequestError):
        return AppError("ai.upstream.connection", "Could not connect to upstream.", 502)
    return AppError("ai.error", str(exc) or "Unknown AI error", 500)


async def post_json(
    *,
    url: str,
    api_key: str,
    body: dict[str, Any],
    log_label: str,
) -> dict[str, Any]:
    """POST JSON to upstream and return parsed response dict."""

    target = normalize_endpoint_url(url)
    log.info("ai %s request url=%s body=%s", log_label, target, json_for_log(body))
    try:
        async with AsyncClient(timeout=client_timeout()) as client:
            resp = await client.post(target, json=body, headers=request_headers(api_key))
            resp.raise_for_status()
            out = resp.json()
            log.info("ai %s response url=%s body=%s", log_label, target, json_for_log(out))
            return out
    except HTTPStatusError as e:
        log_upstream_http_error(url=target, exc=e, method=log_label)
        raise map_upstream_error(e) from None
    except (TimeoutException, RequestError) as e:
        log.warning("ai %s transport error url=%s error=%s", log_label, target, e)
        raise map_upstream_error(e) from None
    except AppError:
        raise
    except Exception as e:
        log.exception("ai %s unexpected error url=%s", log_label, target)
        raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_http_common.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/strategies/http_common.py backend/tests/test_llm_http_common.py
git commit -m "feat(llm): extract shared httpx helpers into http_common"
```

---

### Task 3: TextChatStrategy

**Files:**
- Modify: `backend/app/llm/strategies/base.py`
- Create: `backend/app/llm/strategies/text_chat.py`
- Modify: `backend/tests/test_llm_strategy_unification.py` (partial rewrite)
- Test: same file

- [ ] **Step 1: Write failing text chat strategy test**

Replace the body of `backend/tests/test_llm_strategy_unification.py` with (keep file name for continuity; old provider_kind tests removed):

```python
"""Tests for TextChatStrategy and direct URL posting."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.llm.domain.models import TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies import text_chat as text_chat_module
from app.llm.strategies.http_common import normalize_endpoint_url
from app.llm.strategies.text_chat import TextChatStrategy
from uuid import uuid4


def test_normalize_endpoint_url_keeps_full_configured_url() -> None:
    """Database URL is complete and must not be rewritten."""

    assert (
        normalize_endpoint_url("https://ark.cn-beijing.volces.com/api/v3/responses/")
        == "https://ark.cn-beijing.volces.com/api/v3/responses"
    )


def test_text_chat_complete_posts_to_configured_full_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy POSTs directly to resolved.endpoint_url."""

    captured: dict[str, Any] = {}

    async def fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "id": "chatcmpl-direct",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }

    monkeypatch.setattr(text_chat_module, "post_json", fake_post_json)

    resolved = ResolvedModel(
        model_id=uuid4(),
        model_name="model-a",
        model_type="text",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="key",
    )
    params = TextChatCallParams(messages=[{"role": "user", "content": "hello"}])

    result = asyncio.run(TextChatStrategy().complete(resolved, params))

    assert isinstance(result, TextChatResult)
    assert result.assistant_text() == "ok"
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"]["model"] == "model-a"
    assert captured["body"]["messages"][0]["content"] == "hello"
    assert captured["body"]["stream"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_strategy_unification.py -v`

Expected: FAIL — `TextChatStrategy` not found.

- [ ] **Step 3: Implement TextChatStrategy**

Update `backend/app/llm/strategies/base.py`:

```python
"""Strategy protocols for LLM capability adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.llm.domain.models import (
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import ResolvedModel


class TextChatStrategy(Protocol):
    """Adapter for OpenAI Chat Completions (text and translate model types)."""

    async def complete(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> TextChatResult: ...

    async def stream(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> AsyncIterator[dict]: ...


class EmbeddingStrategy(Protocol):
    """Adapter for OpenAI Embeddings API."""

    async def embed(
        self, resolved: ResolvedModel, params: EmbeddingCallParams
    ) -> EmbeddingResult: ...


class RerankStrategy(Protocol):
    """Adapter for OpenAI-compatible rerank API."""

    async def rerank(
        self, resolved: ResolvedModel, params: RerankCallParams
    ) -> RerankResult: ...
```

Create `backend/app/llm/strategies/text_chat.py`:

```python
"""OpenAI Chat Completions strategy for text and translate models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import orjson
from httpx import AsyncClient, HTTPStatusError, RequestError, TimeoutException

from app.exceptions import AppError
from app.llm.domain.models import TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import (
    client_timeout,
    json_for_log,
    log_upstream_http_error,
    map_upstream_error,
    normalize_endpoint_url,
    post_json,
    request_headers,
    text_for_log,
)
import logging

log = logging.getLogger(__name__)


def _chat_body(resolved: ResolvedModel, params: TextChatCallParams, *, stream: bool) -> dict[str, Any]:
    """Build OpenAI Chat Completions request body."""

    body: dict[str, Any] = {
        "model": resolved.model_name,
        "messages": params.messages,
        "stream": stream,
    }
    optional_fields: list[tuple[str, Any]] = [
        ("temperature", params.temperature),
        ("max_tokens", params.max_tokens),
        ("top_p", params.top_p),
        ("n", params.n),
        ("stop", params.stop),
        ("presence_penalty", params.presence_penalty),
        ("frequency_penalty", params.frequency_penalty),
        ("tools", params.tools),
        ("tool_choice", params.tool_choice),
    ]
    for key, value in optional_fields:
        if value is not None:
            body[key] = value
    return body


def _parse_chat_result(raw: dict[str, Any]) -> TextChatResult:
    """Map upstream JSON into TextChatResult."""

    return TextChatResult(
        id=raw.get("id"),
        model=raw.get("model"),
        usage=raw.get("usage"),
        choices=list(raw.get("choices") or []),
        raw=raw,
    )


class TextChatStrategy:
    """Concrete strategy for OpenAI-compatible chat completions."""

    async def complete(self, resolved: ResolvedModel, params: TextChatCallParams) -> TextChatResult:
        """Perform blocking chat completion."""

        body = _chat_body(resolved, params, stream=False)
        raw = await post_json(
            url=resolved.endpoint_url,
            api_key=resolved.api_key,
            body=body,
            log_label="chat.completions",
        )
        return _parse_chat_result(raw)

    async def stream(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield streamed completion chunks."""

        url = normalize_endpoint_url(resolved.endpoint_url)
        body = _chat_body(resolved, params, stream=True)
        log.info("ai chat.completions request method=stream url=%s body=%s", url, json_for_log(body))
        try:
            async with AsyncClient(timeout=client_timeout()) as client:
                first_chunk: dict[str, Any] | None = None
                last_chunk: dict[str, Any] | None = None
                chunk_count = 0
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    headers=request_headers(resolved.api_key),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        payload = line.removeprefix("data:").strip()
                        if not payload:
                            continue
                        if payload == "[DONE]":
                            break
                        data = orjson.loads(payload)
                        chunk_count += 1
                        if first_chunk is None:
                            first_chunk = data
                        last_chunk = data
                        yield data
                summary = {
                    "chunk_count": chunk_count,
                    "first_chunk": first_chunk,
                    "last_chunk": last_chunk,
                }
                log.info(
                    "ai chat.completions response method=stream url=%s body=%s",
                    url,
                    json_for_log(summary),
                )
        except HTTPStatusError as e:
            log_upstream_http_error(url=url, exc=e, method="stream")
            raise map_upstream_error(e) from None
        except (TimeoutException, RequestError) as e:
            log.warning("ai chat.completions transport error method=stream url=%s error=%s", url, e)
            raise map_upstream_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai stream unexpected error model=%s", resolved.model_name)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_strategy_unification.py -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/strategies/base.py backend/app/llm/strategies/text_chat.py backend/tests/test_llm_strategy_unification.py
git commit -m "feat(llm): add TextChatStrategy with typed request/response"
```

---

### Task 4: EmbeddingStrategy 与 RerankStrategy

**Files:**
- Create: `backend/app/llm/strategies/embedding.py`
- Create: `backend/app/llm/strategies/rerank.py`
- Modify: `backend/app/llm/strategies/__init__.py`
- Test: `backend/tests/test_llm_multi_capability.py`

- [ ] **Step 1: Write failing embedding/rerank tests**

Create `backend/tests/test_llm_multi_capability.py`:

```python
"""Tests for EmbeddingStrategy and RerankStrategy."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.llm.domain.models import EmbeddingCallParams, RerankCallParams
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies import embedding as embedding_module
from app.llm.strategies import rerank as rerank_module
from app.llm.strategies.embedding import EmbeddingStrategy
from app.llm.strategies.rerank import RerankStrategy


@pytest.mark.parametrize(
    "strategy_cls,module,method,params,raw,assert_key",
    [
        (
            EmbeddingStrategy,
            embedding_module,
            "embed",
            EmbeddingCallParams(input="hello", dimensions=8),
            {"data": [{"index": 0, "embedding": [0.1]}], "model": "emb", "usage": {"total_tokens": 1}},
            "data",
        ),
        (
            RerankStrategy,
            rerank_module,
            "rerank",
            RerankCallParams(query="q", documents=["a", "b"], top_n=1),
            {"id": "rerank_1", "results": [{"index": 0, "relevance_score": 0.9}]},
            "results",
        ),
    ],
)
def test_blocking_strategies_post_json(
    strategy_cls: type,
    module: Any,
    method: str,
    params: Any,
    raw: dict[str, Any],
    assert_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding and rerank strategies delegate to post_json and parse results."""

    captured: dict[str, Any] = {}

    async def fake_post_json(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return raw

    monkeypatch.setattr(module, "post_json", fake_post_json)

    resolved = ResolvedModel(
        model_id=uuid4(),
        model_name="model-x",
        model_type="embedding" if assert_key == "data" else "rerank",
        endpoint_url="https://example.com/v1/embeddings" if assert_key == "data" else "https://example.com/v1/rerank",
        api_key="key",
    )
    strategy = strategy_cls()
    result = asyncio.run(getattr(strategy, method)(resolved, params))

    assert captured["body"]["model"] == "model-x"
    assert len(getattr(result, assert_key)) >= 1
    assert result.raw == raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_multi_capability.py -v`

Expected: FAIL — modules missing.

- [ ] **Step 3: Implement embedding and rerank strategies**

Create `backend/app/llm/strategies/embedding.py`:

```python
"""OpenAI Embeddings strategy."""

from __future__ import annotations

from typing import Any

from app.llm.domain.models import EmbeddingCallParams, EmbeddingResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import post_json


class EmbeddingStrategy:
    """Concrete strategy for OpenAI-compatible embeddings."""

    async def embed(self, resolved: ResolvedModel, params: EmbeddingCallParams) -> EmbeddingResult:
        """Perform blocking embedding request."""

        body: dict[str, Any] = {
            "model": resolved.model_name,
            "input": params.input,
            "encoding_format": params.encoding_format,
        }
        if params.dimensions is not None:
            body["dimensions"] = params.dimensions
        raw = await post_json(
            url=resolved.endpoint_url,
            api_key=resolved.api_key,
            body=body,
            log_label="embeddings",
        )
        return EmbeddingResult(
            data=list(raw.get("data") or []),
            model=raw.get("model"),
            usage=raw.get("usage"),
            raw=raw,
        )
```

Create `backend/app/llm/strategies/rerank.py`:

```python
"""OpenAI-compatible rerank strategy."""

from __future__ import annotations

from typing import Any

from app.llm.domain.models import RerankCallParams, RerankResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import post_json


class RerankStrategy:
    """Concrete strategy for OpenAI-compatible rerank APIs."""

    async def rerank(self, resolved: ResolvedModel, params: RerankCallParams) -> RerankResult:
        """Perform blocking rerank request."""

        body: dict[str, Any] = {
            "model": resolved.model_name,
            "query": params.query,
            "documents": params.documents,
        }
        if params.top_n is not None:
            body["top_n"] = params.top_n
        raw = await post_json(
            url=resolved.endpoint_url,
            api_key=resolved.api_key,
            body=body,
            log_label="rerank",
        )
        return RerankResult(
            id=raw.get("id"),
            results=list(raw.get("results") or []),
            raw=raw,
        )
```

Update `backend/app/llm/strategies/__init__.py`:

```python
"""LLM strategy registry."""

from app.llm.strategies.embedding import EmbeddingStrategy
from app.llm.strategies.rerank import RerankStrategy
from app.llm.strategies.text_chat import TextChatStrategy

_TEXT_CHAT_STRATEGY = TextChatStrategy()
_EMBEDDING_STRATEGY = EmbeddingStrategy()
_RERANK_STRATEGY = RerankStrategy()

__all__ = [
    "EmbeddingStrategy",
    "RerankStrategy",
    "TextChatStrategy",
    "get_embedding_strategy",
    "get_rerank_strategy",
    "get_text_chat_strategy",
]


def get_text_chat_strategy() -> TextChatStrategy:
    """Return singleton text chat strategy."""

    return _TEXT_CHAT_STRATEGY


def get_embedding_strategy() -> EmbeddingStrategy:
    """Return singleton embedding strategy."""

    return _EMBEDDING_STRATEGY


def get_rerank_strategy() -> RerankStrategy:
    """Return singleton rerank strategy."""

    return _RERANK_STRATEGY
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_llm_multi_capability.py tests/test_llm_strategy_unification.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/strategies/embedding.py backend/app/llm/strategies/rerank.py backend/app/llm/strategies/__init__.py backend/tests/test_llm_multi_capability.py
git commit -m "feat(llm): add EmbeddingStrategy and RerankStrategy"
```

---

### Task 5: ModelResolver

**Files:**
- Create: `backend/app/llm/service/model_resolver.py`
- Test: `backend/tests/test_llm_model_resolver.py`

- [ ] **Step 1: Write failing resolver tests**

Create `backend/tests/test_llm_model_resolver.py`:

```python
"""Tests for sys_models resolution in app.llm."""

from __future__ import annotations

import uuid

import pytest

from app.exceptions import AppError
from app.llm.domain.resolved_model import CHAT_MODEL_TYPES, ResolvedModel
from app.llm.service.model_resolver import resolve_model
from app.sys.model_provider.domain.db.models import SysModel


class _FakeResult:
    def __init__(self, row: SysModel | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> SysModel | None:
        return self._row


class _FakeSession:
    def __init__(self, row: SysModel | None) -> None:
        self._row = row

    async def execute(self, _stmt):  # noqa: ANN001
        return _FakeResult(self._row)


def _row(**overrides) -> SysModel:  # noqa: ANN003
    ws = uuid.uuid4()
    mid = uuid.uuid4()
    data = dict(
        id=mid,
        workspace_id=ws,
        provider_name="openai",
        model_name="gpt-4o-mini",
        model_type="text",
        enabled=True,
        load_balancing_enabled=False,
        auth_type="api_key",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="secret",
        auth_name=None,
        auth_passwd=None,
        context_size=None,
        max_tokens=None,
        model_config=None,
        create_at=None,
        update_at=None,
    )
    data.update(overrides)
    return SysModel(**data)


@pytest.mark.asyncio
async def test_resolve_model_success() -> None:
    """Enabled model with matching type resolves to ResolvedModel."""

    row = _row()
    session = _FakeSession(row)
    resolved = await resolve_model(
        session,
        workspace_id=row.workspace_id,
        model_id=row.id,
        allowed_types=CHAT_MODEL_TYPES,
    )
    assert isinstance(resolved, ResolvedModel)
    assert resolved.model_name == "gpt-4o-mini"
    assert resolved.endpoint_url.endswith("/chat/completions")


@pytest.mark.asyncio
async def test_resolve_model_type_mismatch() -> None:
    """Wrong model_type for endpoint raises ai.model_type_mismatch."""

    row = _row(model_type="embedding")
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_types=CHAT_MODEL_TYPES,
        )
    assert exc.value.code == "ai.model_type_mismatch"
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_model_misconfigured() -> None:
    """Missing endpoint_url or api_key raises ai.model_misconfigured."""

    row = _row(endpoint_url="", api_key="")
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_types=CHAT_MODEL_TYPES,
        )
    assert exc.value.code == "ai.model_misconfigured"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_model_resolver.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement model_resolver**

Create `backend/app/llm/service/model_resolver.py`:

```python
"""Resolve workspace model_id into upstream credentials."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import normalize_endpoint_url
from app.sys.model_provider.infrastructure import repository as model_repo


async def resolve_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    allowed_types: frozenset[str],
) -> ResolvedModel:
    """Load ``sys_models`` row and validate type, enabled state, and credentials."""

    row = await model_repo.get_for_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    if row is None:
        raise AppError("ai.model_not_found", "模型不存在或不属于当前工作区。", 404)
    if not row.enabled:
        raise AppError("ai.model_disabled", "模型未启用。", 422)
    model_type = (row.model_type or "").strip()
    if model_type not in allowed_types:
        raise AppError(
            "ai.model_type_mismatch",
            f"模型类型 {model_type!r} 不支持当前调用。",
            422,
        )
    endpoint = normalize_endpoint_url((row.endpoint_url or "").strip())
    api_key = (row.api_key or "").strip()
    if not endpoint or not api_key:
        raise AppError("ai.model_misconfigured", "模型缺少 endpoint_url 或 api_key。", 422)
    return ResolvedModel(
        model_id=row.id,
        model_name=row.model_name.strip(),
        model_type=model_type,
        endpoint_url=endpoint,
        api_key=api_key,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_model_resolver.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/service/model_resolver.py backend/tests/test_llm_model_resolver.py
git commit -m "feat(llm): add ModelResolver for model_id credential lookup"
```

---

### Task 6: LlmService 门面

**Files:**
- Create: `backend/app/llm/service/llm_service.py`
- Modify: `backend/app/llm/service/__init__.py`
- Test: `backend/tests/test_llm_service.py`

- [ ] **Step 1: Write failing LlmService test**

Create `backend/tests/test_llm_service.py`:

```python
"""Tests for LlmService orchestration."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.llm.domain.models import ChatMessage, TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import CHAT_MODEL_TYPES, ResolvedModel
from app.llm.service import llm_service as llm_service_module
from app.llm.service.llm_service import LlmService, build_openai_messages


def test_build_openai_messages_order() -> None:
    """Messages order: system, history, trailing user."""

    msgs = build_openai_messages(
        system_prompt="sys",
        user_prompt="tail",
        messages=[ChatMessage(role="user", content="hist")],
    )
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "hist"}
    assert msgs[2] == {"role": "user", "content": "tail"}


def test_complete_chat_resolves_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """complete_chat resolves model then calls text chat strategy."""

    ws = uuid.uuid4()
    mid = uuid.uuid4()
    resolved = ResolvedModel(
        model_id=mid,
        model_name="m",
        model_type="text",
        endpoint_url="https://example.com/v1/chat/completions",
        api_key="k",
    )
    fake_result = TextChatResult(
        choices=[{"message": {"content": "done"}}],
        raw={},
    )

    async def fake_resolve(session, *, workspace_id, model_id, allowed_types):  # noqa: ANN001
        assert workspace_id == ws
        assert model_id == mid
        assert allowed_types == CHAT_MODEL_TYPES
        return resolved

    class _FakeStrategy:
        async def complete(self, r: ResolvedModel, p: TextChatCallParams) -> TextChatResult:
            assert r is resolved
            assert p.messages == [{"role": "user", "content": "hi"}]
            return fake_result

        async def stream(self, r, p):  # noqa: ANN001
            yield {"choices": []}

    monkeypatch.setattr(llm_service_module, "resolve_model", fake_resolve)
    monkeypatch.setattr(llm_service_module, "get_text_chat_strategy", lambda: _FakeStrategy())

    out = asyncio.run(
        LlmService().complete_chat(
            session=None,  # type: ignore[arg-type]
            workspace_id=ws,
            model_id=mid,
            system_prompt=None,
            user_prompt="hi",
            messages=[],
        )
    )
    assert out.assistant_text() == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_service.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement LlmService**

Create `backend/app/llm/service/llm_service.py` (migrate retry logic from `chat_service.py`):

```python
"""Orchestrates multi-capability LLM calls with retries and SSE helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.llm.domain.models import (
    ChatMessage,
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TYPES,
    EMBEDDING_MODEL_TYPES,
    RERANK_MODEL_TYPES,
)
from app.llm.service.model_resolver import resolve_model
from app.llm.strategies import (
    get_embedding_strategy,
    get_rerank_strategy,
    get_text_chat_strategy,
)
from app.llm.strategies.base import EmbeddingStrategy, RerankStrategy, TextChatStrategy

log = logging.getLogger(__name__)

_RETRIABLE_CODES = frozenset(
    {
        "ai.upstream.rate_limited",
        "ai.upstream.timeout",
        "ai.upstream.connection",
        "ai.upstream.unavailable",
        "ai.upstream.error",
    }
)


def build_openai_messages(
    *,
    system_prompt: str | None,
    user_prompt: str | None,
    messages: list[ChatMessage],
) -> list[dict[str, str]]:
    """Flatten prompts into OpenAI-compatible role/content chat arrays."""

    out: list[dict[str, str]] = []
    if system_prompt is not None and system_prompt != "":
        out.append({"role": "system", "content": system_prompt})
    for m in messages:
        out.append({"role": m.role, "content": m.content})
    if user_prompt is not None and user_prompt != "":
        out.append({"role": "user", "content": user_prompt})
    return out


class LlmService:
    """Facade resolving models and delegating to capability strategies."""

    async def _complete_with_retry(self, coro_factory):  # noqa: ANN001
        """Run blocking upstream call with exponential backoff on retriable errors."""

        delay = 0.5
        last: AppError | None = None
        for attempt in range(settings.ai_retry_max_attempts):
            try:
                return await coro_factory()
            except AppError as e:
                last = e
                if e.code not in _RETRIABLE_CODES or attempt >= settings.ai_retry_max_attempts - 1:
                    raise
                log.warning(
                    "ai complete retry attempt=%s/%s code=%s",
                    attempt + 1,
                    settings.ai_retry_max_attempts,
                    e.code,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)
        assert last is not None
        raise last

    async def complete_chat(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_types: frozenset[str] = CHAT_MODEL_TYPES,
    ) -> TextChatResult:
        """Non-streaming chat completion for text or translate models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_types=allowed_types,
        )
        params = TextChatCallParams(
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
        )
        strategy = get_text_chat_strategy()

        async def _call() -> TextChatResult:
            return await strategy.complete(resolved, params)

        return await self._complete_with_retry(_call)

    async def stream_chat(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_types: frozenset[str] = CHAT_MODEL_TYPES,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield upstream chat chunks (no retry)."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_types=allowed_types,
        )
        params = TextChatCallParams(
            messages=build_openai_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages or [],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
        )
        strategy = get_text_chat_strategy()
        async for chunk in strategy.stream(resolved, params):
            yield chunk

    async def stream_sse_lines(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[ChatMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        n: int | None = None,
        stop: list[str] | str | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        allowed_types: frozenset[str] = CHAT_MODEL_TYPES,
    ) -> AsyncIterator[bytes]:
        """Emit SSE-formatted data lines ending with ``[DONE]``."""

        async for chunk in self.stream_chat(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            n=n,
            stop=stop,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            tools=tools,
            tool_choice=tool_choice,
            allowed_types=allowed_types,
        ):
            payload = orjson.dumps(chunk)
            yield b"data: " + payload + b"\n\n"
        yield b"data: [DONE]\n\n"

    async def embed(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        params: EmbeddingCallParams,
    ) -> EmbeddingResult:
        """Non-streaming embedding for embedding-type models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_types=EMBEDDING_MODEL_TYPES,
        )
        strategy = get_embedding_strategy()

        async def _call() -> EmbeddingResult:
            return await strategy.embed(resolved, params)

        return await self._complete_with_retry(_call)

    async def rerank(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        model_id: UUID,
        params: RerankCallParams,
    ) -> RerankResult:
        """Non-streaming rerank for rerank-type models."""

        resolved = await resolve_model(
            session,
            workspace_id=workspace_id,
            model_id=model_id,
            allowed_types=RERANK_MODEL_TYPES,
        )
        strategy = get_rerank_strategy()

        async def _call() -> RerankResult:
            return await strategy.rerank(resolved, params)

        return await self._complete_with_retry(_call)


llm_service = LlmService()
```

Update `backend/app/llm/service/__init__.py`:

```python
"""LLM service exports."""

from app.llm.service.llm_service import LlmService, build_openai_messages, llm_service

__all__ = ["LlmService", "build_openai_messages", "llm_service"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_service.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm/service/llm_service.py backend/app/llm/service/__init__.py backend/tests/test_llm_service.py
git commit -m "feat(llm): add LlmService facade with model_id resolution"
```

---

### Task 7: HTTP API 三端点

**Files:**
- Modify: `backend/app/llm/api/schemas.py`
- Modify: `backend/app/llm/api/router.py`

- [ ] **Step 1: Replace HTTP schemas**

Replace `backend/app/llm/api/schemas.py`:

```python
"""Pydantic request shapes exposed by ``llm`` routers."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    """Inbound chat message tuple mirroring OpenAI chat payloads."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request resolved via workspace model_id."""

    model_id: uuid.UUID
    system_prompt: str | None = None
    user_prompt: str | None = None
    messages: list[ChatMessageIn] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    n: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    stream: bool = True


class EmbeddingRequest(BaseModel):
    """Embedding request resolved via workspace model_id."""

    model_id: uuid.UUID
    input: str | list[str]
    dimensions: int | None = Field(default=None, ge=1)
    encoding_format: str = "float"


class RerankRequest(BaseModel):
    """Rerank request resolved via workspace model_id."""

    model_id: uuid.UUID
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)
    top_n: int | None = Field(default=None, ge=1)
```

- [ ] **Step 2: Replace HTTP router**

Replace `backend/app/llm/api/router.py`:

```python
"""Workspace-scoped LLM proxy endpoints (chat, embeddings, rerank)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.llm.api.schemas import ChatCompletionRequest, EmbeddingRequest, RerankRequest
from app.llm.domain.models import ChatMessage, EmbeddingCallParams, RerankCallParams
from app.llm.domain.resolved_model import CHAT_MODEL_TYPES
from app.llm.service.llm_service import llm_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/llm",
    tags=["llm"],
)


def _to_chat_messages(body: ChatCompletionRequest) -> list[ChatMessage]:
    """Map inbound payload messages into domain ChatMessage rows."""

    return [ChatMessage(role=m.role, content=m.content) for m in body.messages]


@router.post("/chat/completions", response_model=None)
async def create_chat_completion(
    workspace_id: uuid.UUID,
    body: ChatCompletionRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy chat completion via model_id with optional SSE streaming."""

    msgs = _to_chat_messages(body)
    if body.stream:
        return StreamingResponse(
            llm_service.stream_sse_lines(
                session,
                workspace_id=workspace_id,
                model_id=body.model_id,
                system_prompt=body.system_prompt,
                user_prompt=body.user_prompt,
                messages=msgs,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                top_p=body.top_p,
                n=body.n,
                stop=body.stop,
                presence_penalty=body.presence_penalty,
                frequency_penalty=body.frequency_penalty,
                allowed_types=CHAT_MODEL_TYPES,
            ),
            media_type="text/event-stream",
        )
    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        system_prompt=body.system_prompt,
        user_prompt=body.user_prompt,
        messages=msgs,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        n=body.n,
        stop=body.stop,
        presence_penalty=body.presence_penalty,
        frequency_penalty=body.frequency_penalty,
        allowed_types=CHAT_MODEL_TYPES,
    )
    return result.model_dump()


@router.post("/embeddings")
async def create_embedding(
    workspace_id: uuid.UUID,
    body: EmbeddingRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy embedding call via model_id."""

    result = await llm_service.embed(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        params=EmbeddingCallParams(
            input=body.input,
            dimensions=body.dimensions,
            encoding_format=body.encoding_format,
        ),
    )
    return result.model_dump()


@router.post("/rerank")
async def create_rerank(
    workspace_id: uuid.UUID,
    body: RerankRequest,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
):
    """Proxy rerank call via model_id."""

    result = await llm_service.rerank(
        session,
        workspace_id=workspace_id,
        model_id=body.model_id,
        params=RerankCallParams(
            query=body.query,
            documents=body.documents,
            top_n=body.top_n,
        ),
    )
    return result.model_dump()
```

- [ ] **Step 3: Run full LLM test suite**

Run: `cd backend && python -m pytest tests/test_llm_domain_models.py tests/test_llm_http_common.py tests/test_llm_strategy_unification.py tests/test_llm_multi_capability.py tests/test_llm_model_resolver.py tests/test_llm_service.py -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/llm/api/schemas.py backend/app/llm/api/router.py
git commit -m "feat(llm): add model_id HTTP endpoints for chat, embeddings, rerank"
```

---

### Task 8: 迁移业务调用方并清理旧代码

**Files:**
- Modify: `backend/app/rule/service/rule_base_service.py`
- Modify: `backend/app/translate/service/translate_llm.py`
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/app/agent/infrastructure/direct_endpoint_openai_client.py`
- Modify: `backend/app/llm/__init__.py`
- Delete: `backend/app/llm/service/chat_service.py`
- Delete: `backend/app/llm/strategies/openai_compatible.py`

- [ ] **Step 1: Migrate rule_base_service**

In `backend/app/rule/service/rule_base_service.py`:

1. Replace import:
   ```python
   from app.llm.service.llm_service import llm_service
   from app.llm.domain.resolved_model import CHAT_MODEL_TYPES
   ```
2. Remove `_openai_completion_text` helper (use `TextChatResult.assistant_text()`).
3. In `polish_review_rules`, remove manual `endpoint` / `_api_key_for_model` checks (resolver handles misconfigured); keep `model_row.enabled` check or rely on resolver — **prefer removing duplicate checks** and use resolver only.
4. Replace call block (approx lines 233–268):

```python
    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=cfg.model_id,
        system_prompt=system_prompt or None,
        user_prompt=None,
        messages=msgs,
        temperature=None,
        max_tokens=max_tokens,
        allowed_types=frozenset({"text"}),
    )
    return result.assistant_text()
```

- [ ] **Step 2: Migrate translate_llm**

In `backend/app/translate/service/translate_llm.py`:

1. Replace imports with `llm_service` and `frozenset({"translate"})` as `TRANSLATE_MODEL_TYPES`.
2. Simplify `_assert_translate_model` to only verify dict has translate code OR delete it and pass `allowed_types=frozenset({"translate"})` to `llm_service.complete_chat`.
3. Replace `chat_service.complete(...)` with:

```python
    result = await llm_service.complete_chat(
        session,
        workspace_id=workspace_id,
        model_id=model_id,
        system_prompt=system_prompt,
        user_prompt=source_text,
        messages=[ChatMessage(role="user", content=source_text)],
        temperature=0.2,
        max_tokens=max_tokens,
        allowed_types=frozenset({"translate"}),
    )
    text = result.assistant_text()
```

4. Remove `_openai_completion_text`.

- [ ] **Step 3: Update agent imports**

In `chat_model_factory.py` and `direct_endpoint_openai_client.py`, change:

```python
from app.llm.strategies.http_common import normalize_openai_base_url
```

(or `normalize_endpoint_url` — alias exists).

- [ ] **Step 4: Update package exports**

Replace `backend/app/llm/__init__.py`:

```python
"""Multi-capability LLM module with model_id-centric invocation."""

from app.llm.domain.models import (
    ChatMessage,
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.service.llm_service import LlmService, build_openai_messages, llm_service

__all__ = [
    "ChatMessage",
    "EmbeddingCallParams",
    "EmbeddingResult",
    "LlmService",
    "RerankCallParams",
    "RerankResult",
    "ResolvedModel",
    "TextChatCallParams",
    "TextChatResult",
    "build_openai_messages",
    "llm_service",
]
```

- [ ] **Step 5: Delete obsolete files**

```bash
rm backend/app/llm/service/chat_service.py
rm backend/app/llm/strategies/openai_compatible.py
```

- [ ] **Step 6: Run tests including agent regression**

Run: `cd backend && python -m pytest tests/test_llm_domain_models.py tests/test_llm_http_common.py tests/test_llm_strategy_unification.py tests/test_llm_multi_capability.py tests/test_llm_model_resolver.py tests/test_llm_service.py tests/test_agent_chat_model_factory.py tests/test_direct_endpoint_openai_client.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/rule/service/rule_base_service.py backend/app/translate/service/translate_llm.py backend/app/agent/infrastructure/chat_model_factory.py backend/app/agent/infrastructure/direct_endpoint_openai_client.py backend/app/llm/__init__.py
git rm backend/app/llm/service/chat_service.py backend/app/llm/strategies/openai_compatible.py
git commit -m "refactor(llm): migrate callers to llm_service and remove ChatService"
```

---

### Task 9: 文档回填

**Files:**
- Modify: `docs/ai-api.md`
- Modify: `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`

- [ ] **Step 1: Update ai-api.md**

Replace internal call example and HTTP section to document:

- `llm_service.complete_chat(session, workspace_id, model_id, ...)`
- `llm_service.embed(...)` / `llm_service.rerank(...)`
- Three HTTP endpoints with `model_id` only
- New error codes: `ai.model_not_found`, `ai.model_disabled`, `ai.model_type_mismatch`, `ai.model_misconfigured`
- Remove references to `provider_kind`, client-supplied `api_key`, and `ChatService`

- [ ] **Step 2: Mark spec implemented**

In `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`, change status line to:

```markdown
**状态**：已实现（2026-05-28）
```

- [ ] **Step 3: Commit**

```bash
git add docs/ai-api.md docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md
git commit -m "docs: update ai-api for multi-capability model_id LLM module"
```

---

## Spec Coverage Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 三种策略 text/embedding/rerank | Task 3, 4 |
| translate 共用 Chat + service 校验 | Task 6 (`allowed_types`), Task 8 (translate) |
| ResolvedModel + 完整 URL | Task 1, 2, 5 |
| LlmService 重试/流式 | Task 6 |
| HTTP 三端点 + model_type 强校验 | Task 7 |
| 彻底移除 base_url/api_key/model | Task 7, 8 |
| rule/translate 迁移 | Task 8 |
| 错误码 | Task 5, 7 |
| 文档 | Task 9 |
| Agent 不改造 | Task 8 仅 import 路径 |

无 TBD/占位步骤；类型名 `TextChatCallParams` / `ResolvedModel` / `llm_service` 全文一致。

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-28-llm-multi-capability.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做 review，迭代快

**2. Inline Execution** — 在本会话按 Task 顺序执行，批次间设检查点

**你想用哪种方式？**
