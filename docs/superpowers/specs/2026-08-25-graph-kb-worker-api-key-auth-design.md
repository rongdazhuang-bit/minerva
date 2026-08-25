# GraphKB Worker API Key 认证

**状态：** 待实现  
**日期：** 2026-08-25  
**类型：** 安全增强（GraphKB 引擎 Worker 内网调用）  
**Minerva 约定：** 环境变量同步 `backend/.env.example` 与 `backend/.env.dev`；修行为后回填本 spec

**关联文档：**

- [2026-08-23-graph-kb-graphrag-lightrag-design.md](./2026-08-23-graph-kb-graphrag-lightrag-design.md)（GraphKB 总体架构与 Worker 隔离）

---

## 1. 背景与目标

GraphKB 主 API / Celery 通过 HTTP 调用两个独立引擎 Worker：

| Worker | 默认地址 | 环境变量 |
|--------|----------|----------|
| LightRAG | `http://127.0.0.1:8101` | `GRAPH_KB_LIGHTRAG_WORKER_URL` |
| GraphRAG | `http://127.0.0.1:8102` | `GRAPH_KB_GRAPHRAG_WORKER_URL` |

当前 `HttpGraphEngineClient` 发送 POST 时**无任何认证头**。Worker 暴露 `/index`、`/query`、`/export_graph`、`/list_summaries`、`/delete_namespace` 等写读接口，若 Worker 端口被非授权进程访问，可越权操作引擎存储。

**目标：** 为两个 Worker 的 HTTP API 增加 API Key 认证；主 API 出站调用时携带对应 Key；与 Minerva 现有 `API_KEY` 出站习惯（`Authorization: Bearer`）一致。

**范围外：** 用户侧 GraphKB REST API 鉴权（已由 PermissionGateway + ACL 覆盖）；mTLS / OAuth；Worker 对外公开暴露。

---

## 2. 已确认决策

| 项 | 决策 |
|----|------|
| Key 策略 | **各 Worker 独立 Key**（LightRAG / GraphRAG 各一把） |
| 严格模式 | 后端与 Worker **均必须配置** Key；未配置则**拒绝启动**（业务不可用） |
| `/health` | **豁免**认证（探活无需 Key） |
| 传递方式 | `Authorization: Bearer <key>` |
| 实现方案 | **方案 1**：FastAPI HTTP Middleware + 后端 Header 注入 |
| 测试模式 | `GRAPH_KB_ENGINE_CLIENT=fake` 时后端**不校验** Worker Key |

---

## 3. 环境变量

| 变量 | 作用域 | 说明 |
|------|--------|------|
| `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` | 后端 Settings + LightRAG Worker 进程 | LightRAG Worker 调用认证 |
| `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` | 后端 Settings + GraphRAG Worker 进程 | GraphRAG Worker 调用认证 |

### 3.1 同步文件

| 文件 | 内容 |
|------|------|
| `backend/.env.example` | 空占位 + 注释说明用途 |
| `backend/.env.dev` | 固定 dev 占位值（仅本地，非生产密钥） |

**dev 占位值（`.env.dev`）：**

```env
GRAPH_KB_LIGHTRAG_WORKER_API_KEY=dev-graph-kb-lightrag-key
GRAPH_KB_GRAPHRAG_WORKER_API_KEY=dev-graph-kb-graphrag-key
```

Worker 启动脚本**不自动读取** backend `.env`；注释中说明本地需 export 与 `.env.dev` 一致的 Key。

---

## 4. 架构

```
Minerva API / Celery (graph_kb 队列)
        │
        │  POST + Authorization: Bearer <engine-specific-key>
        ▼
┌───────────────────────┐     ┌───────────────────────┐
│ LightRAG Worker :8101 │     │ GraphRAG Worker :8102 │
│ GRAPH_KB_LIGHTRAG_    │     │ GRAPH_KB_GRAPHRAG_    │
│   WORKER_API_KEY      │     │   WORKER_API_KEY      │
│ Middleware 校验 Key   │     │ Middleware 校验 Key   │
│ /health 豁免          │     │ /health 豁免          │
└───────────────────────┘     └───────────────────────┘
```

### 4.1 职责边界

- **Worker**：校验入站 `Authorization: Bearer`；Key 在进程启动时加载，为空则 `sys.exit(1)`。
- **后端**：`HttpGraphEngineClient` 按 `engine` 选择 Key 并注入 Header；`graph_kb_engine_client=http` 时 Settings 启动校验两个 Key 非空。
- **Celery**：与主 API 共用 Settings，无需额外改动。

---

## 5. Worker 实现

### 5.1 新增 `app/auth.py`（两个 Worker 各一份，逻辑相同）

**启动加载：**

```python
def load_expected_api_key(env_name: str) -> str:
    key = os.environ.get(env_name, "").strip()
    if not key:
        print(f"[error] {env_name} is required", file=sys.stderr)
        sys.exit(1)
    return key
```

| Worker | `env_name` |
|--------|------------|
| LightRAG | `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` |
| GraphRAG | `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` |

模块 import 时调用 `load_expected_api_key`，确保 uvicorn 启动前失败。

**HTTP Middleware：**

| 请求路径 | 行为 |
|----------|------|
| `/health` | 放行 |
| `/docs`、`/openapi.json`、`/redoc` | 放行（本地调试 OpenAPI） |
| 其他 | 校验 `Authorization: Bearer <token>` |

校验规则：

1. Header 缺失或非 `Bearer` 前缀 → 401
2. Token 与期望值用 `secrets.compare_digest` 比较 → 不匹配 401
3. 401 响应体：`{"detail": "Unauthorized"}`（不泄露 Key 配置状态）

`main.py` 在创建 `FastAPI` 实例后注册 middleware。

---

## 6. 后端实现

### 6.1 Settings（`backend/app/config.py`）

新增字段：

```python
graph_kb_lightrag_worker_api_key: str  # GRAPH_KB_LIGHTRAG_WORKER_API_KEY
graph_kb_graphrag_worker_api_key: str  # GRAPH_KB_GRAPHRAG_WORKER_API_KEY
```

**启动校验**（`@model_validator(mode="after")`）：

- 当 `graph_kb_engine_client == "http"` 时，`graph_kb_lightrag_worker_api_key` 与 `graph_kb_graphrag_worker_api_key` strip 后均不得为空。
- 违反时 `ValueError`，阻止 API 进程启动，错误信息指明变量名。
- 当 `graph_kb_engine_client == "fake"` 时跳过校验（单元测试）。

### 6.2 HttpGraphEngineClient（`backend/app/graph_kb/engine/http_client.py`）

```python
def _auth_headers(engine: str) -> dict[str, str]:
    if engine == ENGINE_LIGHTRAG:
        key = settings.graph_kb_lightrag_worker_api_key.strip()
    elif engine == ENGINE_GRAPHRAG:
        key = settings.graph_kb_graphrag_worker_api_key.strip()
    else:
        raise AppError(...)
    return {"Authorization": f"Bearer {key}"}
```

`_post()` 调用 `client.post(url, json=payload, headers=_auth_headers(engine))`。

### 6.3 错误映射

| Worker HTTP 状态 | AppError code | HTTP | 用户可见消息 |
|------------------|---------------|------|--------------|
| 401 | `graph_kb.worker_unauthorized` | 502 | 图谱引擎 Worker 认证失败。 |
| 其他 4xx/5xx | `graph_kb.worker_error` | 502 | 图谱引擎 Worker 返回错误: HTTP {status} |
| 连接失败 | `graph_kb.worker_unavailable` | 503 | 图谱引擎 Worker 不可用。 |

401 单独映射便于运维区分「Key 不一致」与「引擎执行错误」。

---

## 7. 测试

### 7.1 Worker 单元测试（`tests/test_auth.py`）

每个 Worker 新增：

| 用例 | 期望 |
|------|------|
| 无 `Authorization` | 401 |
| 错误 Bearer token | 401 |
| 正确 Bearer token | 200（对 `/index` 等已有 fake 用例端点） |
| `GET /health` 无 Header | 200 |

现有 `test_root.py`、`test_fake_api.py` 等须在测试 setup 中 `monkeypatch.setenv` Key 并 reload app；TestClient 请求带 `headers={"Authorization": "Bearer test-key"}`。

### 7.2 后端单元测试

| 文件 | 用例 |
|------|------|
| `test_graph_kb_engine_client.py` | Mock transport 断言 POST 含正确 `Authorization`；模拟 401 → `graph_kb.worker_unauthorized` |
| config 相关测试 | `graph_kb_engine_client=http` 且 Key 为空 → Settings 校验失败 |

`GRAPH_KB_ENGINE_CLIENT=fake` 的现有测试无需改动。

---

## 8. 文档与脚本

| 文件 | 变更 |
|------|------|
| `README.md` | GraphKB 环境变量表增加两个 `*_WORKER_API_KEY` |
| `scripts/run-graph-kb-lightrag-worker.cmd` | 注释：须设置 `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` |
| `scripts/run-graph-kb-graphrag-worker.cmd` | 注释：须设置 `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` |

---

## 9. 改动文件清单

| 文件 | 变更类型 |
|------|----------|
| `workers/graph-kb-lightrag/app/auth.py` | 新增 |
| `workers/graph-kb-graphrag/app/auth.py` | 新增 |
| `workers/graph-kb-lightrag/app/main.py` | 挂载 middleware |
| `workers/graph-kb-graphrag/app/main.py` | 挂载 middleware |
| `workers/graph-kb-lightrag/tests/test_auth.py` | 新增 |
| `workers/graph-kb-graphrag/tests/test_auth.py` | 新增 |
| `workers/graph-kb-*/tests/test_*.py` | 适配 Key |
| `backend/app/config.py` | 字段 + 启动校验 |
| `backend/app/graph_kb/engine/http_client.py` | Header + 401 映射 |
| `backend/.env.example` | 新变量 |
| `backend/.env.dev` | dev 占位值 |
| `backend/tests/test_graph_kb_engine_client.py` | 新用例 |
| `README.md` | 环境变量说明 |

---

## 10. 部署与轮换

1. 为生产环境生成足够长度的随机 Key（建议 ≥ 32 字符），分别写入后端与对应 Worker 的环境配置。
2. 先部署 Worker（带 Key），再部署后端（带匹配 Key），避免短暂 401。
3. 轮换 Key：更新 Worker 与后端配置后滚动重启；两把 Key 可独立轮换。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 本地忘记配置 Key，Worker/API 无法启动 | `.env.dev` 提供 dev 占位值；README 与脚本注释说明 |
| Key 不一致导致 502 | 独立错误码 `worker_unauthorized`；日志记录 HTTP 401（不记录 Key 明文） |
| 两个 Worker 的 `auth.py` 重复 | 接受：独立 venv，复制成本低；注释注明需同步修改 |
