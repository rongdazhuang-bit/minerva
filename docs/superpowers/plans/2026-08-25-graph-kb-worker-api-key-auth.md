# GraphKB Worker API Key 认证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 GraphKB 的 LightRAG / GraphRAG 独立 Worker HTTP API 增加 `Authorization: Bearer` API Key 认证，并在主 API `HttpGraphEngineClient` 出站调用时注入对应 Key。

**Architecture:** 各 Worker 在 `app/auth.py` 启动时加载本 Worker 专属环境变量 Key（为空则进程退出）；FastAPI HTTP Middleware 对除 `/health` 与 OpenAPI 文档路径外的请求校验 Bearer token（`secrets.compare_digest`）。后端 `Settings` 在 `GRAPH_KB_ENGINE_CLIENT=http` 时强制两个 Key 非空；`HttpGraphEngineClient._post` 按 engine 注入 Header；Worker 401 映射为 `graph_kb.worker_unauthorized`。

**Tech Stack:** FastAPI, httpx, Pydantic v2 Settings, pytest, `secrets.compare_digest`

**设计依据:** `docs/superpowers/specs/2026-08-25-graph-kb-worker-api-key-auth-design.md`

## Global Constraints

- 环境变量变更必须同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`。
- Key 变量名：`GRAPH_KB_LIGHTRAG_WORKER_API_KEY`、`GRAPH_KB_GRAPHRAG_WORKER_API_KEY`（各 Worker 独立，严格模式，两端均必填）。
- 认证头：`Authorization: Bearer <key>`；`/health` 豁免；OpenAPI 路径（`/docs`、`/openapi.json`、`/redoc`）豁免。
- `GRAPH_KB_ENGINE_CLIENT=fake` 时后端**不校验** Worker Key（现有 fake 单测无需改动）。
- 日志与错误响应禁止泄露 Key 明文；401 响应体固定 `{"detail": "Unauthorized"}`。
- 类与方法必须有 docstring（code-comments skill）。
- Worker 测试须在 `import app.main` **之前**设置对应 `GRAPH_KB_*_WORKER_API_KEY` 环境变量（auth 模块 import 时加载 Key）。

---

## 文件结构

| 路径 | 职责 |
|------|------|
| `workers/graph-kb-lightrag/app/auth.py` | LightRAG Worker Key 加载 + Middleware |
| `workers/graph-kb-graphrag/app/auth.py` | GraphRAG Worker Key 加载 + Middleware |
| `workers/graph-kb-lightrag/app/main.py` | 注册 auth middleware |
| `workers/graph-kb-graphrag/app/main.py` | 注册 auth middleware |
| `workers/graph-kb-*/tests/test_auth.py` | Worker 认证单测 |
| `workers/graph-kb-*/tests/test_*.py` | 现有测试适配 Key + Header |
| `backend/app/config.py` | Settings 字段 + `validate_graph_kb_worker_api_keys` |
| `backend/.env.example`, `backend/.env.dev` | 同步 Key 环境变量 |
| `backend/app/graph_kb/engine/http_client.py` | 出站 Header + 401 映射 |
| `backend/tests/test_graph_kb_engine_client.py` | Header 断言 + 401 用例 |
| `backend/tests/test_graph_kb_worker_api_key_config.py` | Settings 启动校验 |
| `README.md` | GraphKB 环境变量表补充 |
| `scripts/run-graph-kb-*-worker.cmd` | 注释补充 Key 要求 |

---

### Task 1: LightRAG Worker 认证模块

**Files:**
- Create: `workers/graph-kb-lightrag/app/auth.py`
- Modify: `workers/graph-kb-lightrag/app/main.py`
- Create: `workers/graph-kb-lightrag/tests/test_auth.py`

**Interfaces:**
- Consumes: 无
- Produces: `EXPECTED_API_KEY: str`（模块级常量）；`api_key_middleware(request, call_next) -> Response`

- [ ] **Step 1: Write the failing test**

Create `workers/graph-kb-lightrag/tests/test_auth.py`:

```python
"""API key middleware tests for the LightRAG worker."""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient

_TEST_KEY = "test-lightrag-worker-key"
os.environ["GRAPH_KB_WORKER_FAKE"] = "1"
os.environ["GRAPH_KB_LIGHTRAG_WORKER_API_KEY"] = _TEST_KEY

import app.main as main_mod

_AUTH = {"Authorization": f"Bearer {_TEST_KEY}"}


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient against a reloaded app with fake store."""

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_health_does_not_require_api_key(client: TestClient) -> None:
    """GET /health must stay unauthenticated for probes."""

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_without_authorization_returns_401(client: TestClient) -> None:
    """Business endpoints must reject missing Bearer token."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


def test_post_with_wrong_api_key_returns_401(client: TestClient) -> None:
    """Mismatched Bearer token must return 401."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_post_with_valid_api_key_succeeds(client: TestClient) -> None:
    """Valid Bearer token must allow business endpoints."""

    wid = "11111111-1111-1111-1111-111111111111"
    gid = "22222222-2222-2222-2222-222222222222"
    resp = client.post(
        "/export_graph",
        json={"workspace_id": wid, "graph_id": gid, "engine": "lightrag"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run from repo root:

```bash
cd workers/graph-kb-lightrag && python -m pytest tests/test_auth.py -v
```

Expected: FAIL — `ModuleNotFoundError` or import error for `app.auth`, or 200 instead of 401 on unauthenticated POST.

- [ ] **Step 3: Write minimal implementation**

Create `workers/graph-kb-lightrag/app/auth.py`:

```python
"""Bearer API key authentication for the LightRAG graph-kb worker."""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.responses import JSONResponse

_ENV_NAME = "GRAPH_KB_LIGHTRAG_WORKER_API_KEY"
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


def load_expected_api_key(env_name: str) -> str:
    """Load and validate the worker API key from the environment."""

    key = (os.environ.get(env_name) or "").strip()
    if not key:
        print(f"[error] {env_name} is required", file=sys.stderr)
        sys.exit(1)
    return key


EXPECTED_API_KEY: str = load_expected_api_key(_ENV_NAME)


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Parse ``Authorization: Bearer <token>``; return token or None."""

    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def api_key_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject unauthenticated requests except public probe and OpenAPI paths."""

    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if token is None or not secrets.compare_digest(token, EXPECTED_API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)
```

Modify `workers/graph-kb-lightrag/app/main.py` — add import and register middleware after `app = FastAPI(...)`:

```python
from app.auth import api_key_middleware

app = FastAPI(title="Minerva GraphKB LightRAG Worker", version="0.1.0")
app.middleware("http")(api_key_middleware)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd workers/graph-kb-lightrag && python -m pytest tests/test_auth.py -v
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add workers/graph-kb-lightrag/app/auth.py workers/graph-kb-lightrag/app/main.py workers/graph-kb-lightrag/tests/test_auth.py
git commit -m "feat(graph-kb): add Bearer API key auth to LightRAG worker"
```

---

### Task 2: LightRAG Worker 现有测试适配

**Files:**
- Modify: `workers/graph-kb-lightrag/tests/test_fake_api.py`
- Modify: `workers/graph-kb-lightrag/tests/test_store.py`（若存在对 `app.main` 的 HTTP 调用则适配；纯 store 单测可跳过）

**Interfaces:**
- Consumes: `EXPECTED_API_KEY` / env `GRAPH_KB_LIGHTRAG_WORKER_API_KEY`
- Produces: 所有 LightRAG worker HTTP 测试带 `Authorization: Bearer test-lightrag-worker-key`

- [ ] **Step 1: Update existing tests**

In `workers/graph-kb-lightrag/tests/test_fake_api.py`, after `os.environ["GRAPH_KB_WORKER_FAKE"] = "1"` add:

```python
os.environ["GRAPH_KB_LIGHTRAG_WORKER_API_KEY"] = "test-lightrag-worker-key"
```

Add module constant:

```python
_AUTH = {"Authorization": "Bearer test-lightrag-worker-key"}
```

Add `headers=_AUTH` to every `client.post(...)` and `client.get(...)` call except `/health` if any.

Because `app.main` is imported at module level **before** the new env line unless reordered, **move** the `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` assignment **above** `from app.main import app`, or switch to `importlib.reload` pattern like `test_auth.py`.

Recommended: replace top of file with:

```python
import os

os.environ["GRAPH_KB_WORKER_FAKE"] = "1"
os.environ["GRAPH_KB_LIGHTRAG_WORKER_API_KEY"] = "test-lightrag-worker-key"

from fastapi.testclient import TestClient

from app.main import app

_AUTH = {"Authorization": "Bearer test-lightrag-worker-key"}
```

- [ ] **Step 2: Run all LightRAG worker tests**

```bash
cd workers/graph-kb-lightrag && python -m pytest tests/ -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add workers/graph-kb-lightrag/tests/
git commit -m "test(graph-kb): adapt LightRAG worker tests for API key auth"
```

---

### Task 3: GraphRAG Worker 认证模块

**Files:**
- Create: `workers/graph-kb-graphrag/app/auth.py`
- Modify: `workers/graph-kb-graphrag/app/main.py`
- Create: `workers/graph-kb-graphrag/tests/test_auth.py`

**Interfaces:**
- Consumes: Task 1 的 `auth.py` 模式（复制并改 `_ENV_NAME`）
- Produces: GraphRAG 版 `api_key_middleware`；env `GRAPH_KB_GRAPHRAG_WORKER_API_KEY`

- [ ] **Step 1: Write the failing test**

Create `workers/graph-kb-graphrag/tests/test_auth.py` — 与 Task 1 结构相同，替换：

- `_TEST_KEY = "test-graphrag-worker-key"`
- `os.environ["GRAPH_KB_GRAPHRAG_WORKER_API_KEY"] = _TEST_KEY`
- payload 中 `"engine": "graphrag"`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd workers/graph-kb-graphrag && python -m pytest tests/test_auth.py -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Create `workers/graph-kb-graphrag/app/auth.py` — 与 LightRAG 版相同，仅改：

```python
_ENV_NAME = "GRAPH_KB_GRAPHRAG_WORKER_API_KEY"
```

Modify `workers/graph-kb-graphrag/app/main.py` 注册 middleware（同 Task 1）。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd workers/graph-kb-graphrag && python -m pytest tests/test_auth.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add workers/graph-kb-graphrag/app/auth.py workers/graph-kb-graphrag/app/main.py workers/graph-kb-graphrag/tests/test_auth.py
git commit -m "feat(graph-kb): add Bearer API key auth to GraphRAG worker"
```

---

### Task 4: GraphRAG Worker 现有测试适配

**Files:**
- Modify: `workers/graph-kb-graphrag/tests/test_root.py`

**Interfaces:**
- Consumes: env `GRAPH_KB_GRAPHRAG_WORKER_API_KEY`
- Produces: GraphRAG worker HTTP 测试均带 Bearer Header

- [ ] **Step 1: Update `test_root.py`**

在每个使用 `TestClient` 的测试函数中：

1. `monkeypatch.setenv("GRAPH_KB_GRAPHRAG_WORKER_API_KEY", "test-graphrag-worker-key")` **在** `importlib.reload(main_mod)` **之前**。
2. 定义 `_AUTH = {"Authorization": "Bearer test-graphrag-worker-key"}`。
3. 所有 `client.post(...)` 加 `headers=_AUTH`。

`test_graphrag_root_nests_workspace_then_graph` 不调用 HTTP，无需改动。

- [ ] **Step 2: Run all GraphRAG worker tests**

```bash
cd workers/graph-kb-graphrag && python -m pytest tests/ -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add workers/graph-kb-graphrag/tests/
git commit -m "test(graph-kb): adapt GraphRAG worker tests for API key auth"
```

---

### Task 5: 后端 Settings 与环境变量

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`
- Create: `backend/tests/test_graph_kb_worker_api_key_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `settings.graph_kb_lightrag_worker_api_key: str`；`settings.graph_kb_graphrag_worker_api_key: str`；`Settings.validate_graph_kb_worker_api_keys()`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_graph_kb_worker_api_key_config.py`:

```python
"""Settings validation for GraphKB worker API keys."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_requires_worker_keys_when_engine_client_is_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP engine client mode must require both worker API keys."""

    monkeypatch.setenv("GRAPH_KB_ENGINE_CLIENT", "http")
    monkeypatch.delenv("GRAPH_KB_LIGHTRAG_WORKER_API_KEY", raising=False)
    monkeypatch.delenv("GRAPH_KB_GRAPHRAG_WORKER_API_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings()
    msg = str(exc.value)
    assert "GRAPH_KB_LIGHTRAG_WORKER_API_KEY" in msg or "lightrag" in msg.lower()


def test_settings_skips_worker_key_check_when_engine_client_is_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake engine client must not require worker API keys."""

    monkeypatch.setenv("GRAPH_KB_ENGINE_CLIENT", "fake")
    monkeypatch.delenv("GRAPH_KB_LIGHTRAG_WORKER_API_KEY", raising=False)
    monkeypatch.delenv("GRAPH_KB_GRAPHRAG_WORKER_API_KEY", raising=False)
    settings = Settings()
    assert settings.graph_kb_engine_client == "fake"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_graph_kb_worker_api_key_config.py -v
```

Expected: FAIL — first test passes accidentally if keys already in env; second may pass. First test should fail when keys empty **after** validator is added. Run with explicit empty:

```bash
GRAPH_KB_ENGINE_CLIENT=http GRAPH_KB_LIGHTRAG_WORKER_API_KEY= GRAPH_KB_GRAPHRAG_WORKER_API_KEY= pytest tests/test_graph_kb_worker_api_key_config.py::test_settings_requires_worker_keys_when_engine_client_is_http -v
```

- [ ] **Step 3: Write minimal implementation**

In `backend/app/config.py`, after `graph_kb_engine_client` field add:

```python
    graph_kb_lightrag_worker_api_key: str = Field(
        default="",
        description="LightRAG Worker HTTP API Key（Authorization: Bearer）。",
        validation_alias=AliasChoices(
            "GRAPH_KB_LIGHTRAG_WORKER_API_KEY",
            "graph_kb_lightrag_worker_api_key",
        ),
    )
    graph_kb_graphrag_worker_api_key: str = Field(
        default="",
        description="GraphRAG Worker HTTP API Key（Authorization: Bearer）。",
        validation_alias=AliasChoices(
            "GRAPH_KB_GRAPHRAG_WORKER_API_KEY",
            "graph_kb_graphrag_worker_api_key",
        ),
    )
```

Add new validator after `validate_agent_memory_backend_config`:

```python
    @model_validator(mode="after")
    def validate_graph_kb_worker_api_keys(self) -> Self:
        """When using HTTP engine client, require both worker API keys."""

        if self.graph_kb_engine_client != "http":
            return self
        if not self.graph_kb_lightrag_worker_api_key.strip():
            raise ValueError(
                "GRAPH_KB_ENGINE_CLIENT=http requires GRAPH_KB_LIGHTRAG_WORKER_API_KEY"
            )
        if not self.graph_kb_graphrag_worker_api_key.strip():
            raise ValueError(
                "GRAPH_KB_ENGINE_CLIENT=http requires GRAPH_KB_GRAPHRAG_WORKER_API_KEY"
            )
        return self
```

Update `backend/.env.example` after `GRAPH_KB_GRAPHRAG_WORKER_URL` line:

```env
# Worker HTTP API Key（Authorization: Bearer）；GRAPH_KB_ENGINE_CLIENT=http 时必填
GRAPH_KB_LIGHTRAG_WORKER_API_KEY=
GRAPH_KB_GRAPHRAG_WORKER_API_KEY=
```

Update `backend/.env.dev`:

```env
GRAPH_KB_LIGHTRAG_WORKER_API_KEY=dev-graph-kb-lightrag-key
GRAPH_KB_GRAPHRAG_WORKER_API_KEY=dev-graph-kb-graphrag-key
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_graph_kb_worker_api_key_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_graph_kb_worker_api_key_config.py
git commit -m "feat(graph-kb): require worker API keys when engine client is http"
```

---

### Task 6: HttpGraphEngineClient 出站认证与 401 映射

**Files:**
- Modify: `backend/app/graph_kb/engine/http_client.py`
- Modify: `backend/tests/test_graph_kb_engine_client.py`

**Interfaces:**
- Consumes: `settings.graph_kb_lightrag_worker_api_key`, `settings.graph_kb_graphrag_worker_api_key`
- Produces: `_auth_headers(engine: str) -> dict[str, str]`；401 → `AppError("graph_kb.worker_unauthorized", ..., 502)`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_graph_kb_engine_client.py`:

```python
@pytest.mark.asyncio
async def test_http_post_includes_authorization_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outbound worker calls must send Authorization: Bearer with engine-specific key."""

    import json

    from app.config import settings

    monkeypatch.setattr(settings, "graph_kb_lightrag_worker_api_key", "lightrag-secret")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"entities": [], "relations": []})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    llm = ModelEndpoint("http://llm", "key", "model")
    w, g = uuid4(), uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "d.txt", "hello")],
            llm=llm,
            embedding=llm,
        )
    )
    assert captured["authorization"] == "Bearer lightrag-secret"


@pytest.mark.asyncio
async def test_http_worker_401_maps_to_unauthorized_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker HTTP 401 must map to graph_kb.worker_unauthorized."""

    from app.config import settings

    monkeypatch.setattr(settings, "graph_kb_lightrag_worker_api_key", "k")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    client = HttpGraphEngineClient(transport=transport)
    with pytest.raises(AppError) as exc:
        await client.export_graph(
            engine=ENGINE_LIGHTRAG, workspace_id=uuid4(), graph_id=uuid4()
        )
    assert exc.value.code == "graph_kb.worker_unauthorized"
    assert exc.value.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_graph_kb_engine_client.py::test_http_post_includes_authorization_bearer_header tests/test_graph_kb_engine_client.py::test_http_worker_401_maps_to_unauthorized_error -v
```

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `backend/app/graph_kb/engine/http_client.py`, add:

```python
def _auth_headers(engine: str) -> dict[str, str]:
    """Build Authorization header for the given engine worker."""

    if engine == ENGINE_LIGHTRAG:
        key = settings.graph_kb_lightrag_worker_api_key.strip()
    elif engine == ENGINE_GRAPHRAG:
        key = settings.graph_kb_graphrag_worker_api_key.strip()
    else:
        raise AppError("graph_kb.invalid_engine", f"未知引擎: {engine}", 400)
    return {"Authorization": f"Bearer {key}"}
```

In `_post`, change:

```python
response = await client.post(url, json=payload, headers=_auth_headers(engine))
```

In `except httpx.HTTPStatusError`, before generic handler:

```python
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise AppError(
                    "graph_kb.worker_unauthorized",
                    "图谱引擎 Worker 认证失败。",
                    502,
                ) from exc
            raise AppError(
                "graph_kb.worker_error",
                f"图谱引擎 Worker 返回错误: HTTP {exc.response.status_code}",
                502,
            ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_graph_kb_engine_client.py -v
```

Expected: PASS（全部用例）

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/engine/http_client.py backend/tests/test_graph_kb_engine_client.py
git commit -m "feat(graph-kb): send Bearer token to workers and map 401 errors"
```

---

### Task 7: 文档与启动脚本注释

**Files:**
- Modify: `README.md`
- Modify: `scripts/run-graph-kb-lightrag-worker.cmd`
- Modify: `scripts/run-graph-kb-graphrag-worker.cmd`

**Interfaces:**
- Consumes: 无
- Produces: 文档说明两个 `*_WORKER_API_KEY` 必须与 backend `.env.dev` 一致

- [ ] **Step 1: Update README GraphKB 环境变量表**

在 `README.md`「独立引擎 Worker」环境变量表增加两行：

| `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` | LightRAG Worker Bearer 认证（`http` 模式必填） |
| `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` | GraphRAG Worker Bearer 认证（`http` 模式必填） |

补充一句：本地开发时 Worker 进程须 export 与 `backend/.env.dev` 相同的 Key。

- [ ] **Step 2: Update worker 启动脚本注释**

`scripts/run-graph-kb-lightrag-worker.cmd` REM 块增加：

```cmd
REM Env: GRAPH_KB_LIGHTRAG_WORKER_API_KEY (required) must match backend/.env.dev
```

`scripts/run-graph-kb-graphrag-worker.cmd` REM 块增加：

```cmd
REM Env: GRAPH_KB_GRAPHRAG_WORKER_API_KEY (required) must match backend/.env.dev
```

- [ ] **Step 3: Commit**

```bash
git add README.md scripts/run-graph-kb-lightrag-worker.cmd scripts/run-graph-kb-graphrag-worker.cmd
git commit -m "docs(graph-kb): document worker API key env vars"
```

---

### Task 8: 全量回归

**Files:** 无新文件

- [ ] **Step 1: Run backend GraphKB tests**

```bash
cd backend && GRAPH_KB_ENGINE_CLIENT=fake pytest tests/test_graph_kb_*.py -q
```

Expected: PASS

- [ ] **Step 2: Run worker tests**

```bash
cd workers/graph-kb-lightrag && python -m pytest tests/ -q
cd ../graph-kb-graphrag && python -m pytest tests/ -q
```

Expected: PASS

- [ ] **Step 3: Update design spec status (optional)**

In `docs/superpowers/specs/2026-08-25-graph-kb-worker-api-key-auth-design.md`, change **状态** from「待实现」to「已实现」.

```bash
git add docs/superpowers/specs/2026-08-25-graph-kb-worker-api-key-auth-design.md
git commit -m "docs: mark GraphKB worker API key auth spec as implemented"
```

---

## Spec Coverage Checklist

| Spec § | Task |
|--------|------|
| §2 已确认决策 | Task 1–7 |
| §3 环境变量 | Task 5, 7 |
| §5 Worker Middleware | Task 1, 3 |
| §6 后端 Settings + http_client | Task 5, 6 |
| §7 测试 | Task 1–6, 8 |
| §8 文档脚本 | Task 7 |
| §10 部署轮换 | Task 7（README 说明） |

## Type / Name Consistency

- Env: `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` / `GRAPH_KB_GRAPHRAG_WORKER_API_KEY`
- Settings: `graph_kb_lightrag_worker_api_key` / `graph_kb_graphrag_worker_api_key`
- AppError code: `graph_kb.worker_unauthorized`
- Middleware: `api_key_middleware`（两 Worker 同名）
- Header helper: `_auth_headers(engine: str) -> dict[str, str]`
