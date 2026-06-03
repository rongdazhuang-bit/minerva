# Agent 记忆双后端：SQL 表 vs mem0（pgvector + Neo4j）设计

**日期**：2026-06-02  
**状态**：已实现（2026-06-02，Celery 压缩批处理为占位实现）  
**计划**：`docs/superpowers/plans/2026-06-02-agent-mem0-memory.md`  
**范围**：Agent 长期记忆的存储与召回采用**策略模式**、**互斥切换**（`sql` | `mem0`）；mem0 路径使用 **PostgreSQL pgvector**（库 `minerva_memory`）+ **Neo4j 图存储**双存储；持久化人物画像表 + 运行时现场画像分层；mem0 专属 Celery 压缩与管理端 CRUD。SQL 路径保持现网行为不变。

**关联文档**：

- `docs/agent-module-design.md` §8 长期记忆（实现后须回填）
- `docs/superpowers/specs/2026-05-16-agent-langgraph-redesign-design.md`
- `.cursor/skills/minerva-conventions/SKILL.md`（无 DB 外键、环境变量同步）

---

## 1. 目标与成功标准

### 1.1 目标

1. **集成 mem0**：`AGENT_MEMORY_BACKEND=mem0` 时通过 mem0 SDK 完成记忆写入与语义/图召回。
2. **双存储**：同一 PG 实例下独立库 `minerva_memory`（pgvector）+ 独立 Neo4j 实例（图记忆）；均可通过环境变量配置。
3. **与 SQL 记忆并存**：代码层两套实现共存，运行时**互斥**只启用其一；`sql` 时行为与现网 `AgentMemoryStore` 一致。
4. **策略模式**：`MemoryRetrieveStrategy` 与 `MemoryPersistStrategy` 分离，互不耦合；工厂按配置注入成对实现。
5. **压缩与画像**：mem0 自带 infer/update；可选 Run 内 LLM 压缩（默认关）；Run 时现场 session 画像（默认不落库）；工作区/会话级**持久化画像**可管理端编辑；Celery 对过期/冗余记忆做摘要合并（mem0 专属）。
6. **配置**：mem0 的 LLM / Embedder / PG / Neo4j 均使用 **独立环境变量**（`MEM0_*`），不读 `sys_models` 表。

### 1.2 成功标准

- `AGENT_MEMORY_BACKEND=sql`：现有测试与 Run/SSE 行为无回归。
- `AGENT_MEMORY_BACKEND=mem0`：Run 开始能召回记忆并注入 Planner；Run 成功后后台写入 mem0；`memory.retrieved` / `memory.persist` SSE 与节点可观测。
- 启动校验：mem0 模式缺少 `MEM0_DATABASE_URL`（或 PG 分项）或启用图时缺少 `MEM0_NEO4J_*` → 进程启动失败。
- 管理端（仅 mem0）：可查看/删除 mem0 记忆、编辑工作区/会话级持久画像。
- 环境变量已同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| 后端切换 | **互斥**：`sql` \| `mem0`，环境变量 `AGENT_MEMORY_BACKEND` |
| 架构 | **方案 1**：双 Protocol + 工厂 |
| mem0 隔离 | **会话级**：`user_id` = `workspace_id`，`run_id` = `session_id` |
| 向量库 | PG **`minerva_memory`** + `pgvector` extension |
| 图库 | **Neo4j**（`graph_store.provider=neo4j`），`pip install "mem0ai[graph]"` |
| Embedding/LLM | **mem0 独立配置** `MEM0_LLM_*` / `MEM0_EMBEDDER_*` |
| Run 时 session 画像 | mem0 `search` 拼接；可选 LLM 合成（`AGENT_MEMORY_PROFILE_LLM_ENABLED`，**默认 false**） |
| 持久画像 | 表 `agent_memory_profile`（workspace / session 两层），管理端可编辑 |
| Run 内 LLM 压缩 | `AGENT_MEMORY_LLM_COMPRESS_ENABLED`，**默认 false** |
| Celery 压缩 / 管理端 | **仅 mem0**；`sql` 保持现状 |
| SQL → mem0 数据迁移 | **不做**；切换后数据隔离 |
| Neo4j 降级 | `MEM0_GRAPH_ENABLED=false` 时仅 pgvector（dev 无 Neo4j） |

---

## 2. 总体架构

```
AGENT_MEMORY_BACKEND = sql | mem0
         │
    ┌────┴────┐
    ▼         ▼
 Sql*      Mem0*
 Strategy  Strategy
    │         │
    ▼         ├─► minerva_memory (pgvector)  ─ semantic search
    ▼         └─► Neo4j (graph_store)        ─ entities / relations
agent_long_term_memory
agent_message (fallback)
agent_memory_profile (mem0 模式：持久画像)
```

### 2.1 Run 主路径（mem0）

1. **`memory.retrieve`**：`Mem0RetrieveStrategy.retrieve` → `MemoryHit[]`；`build_planner_context` 读取 `agent_memory_profile`（workspace + session 行）+ 现场 session 画像（search，可选 LLM）+ 格式化 hits。
2. **Planner / Executor / Synthesizer**：使用 `memory_context` 字符串前缀（与现网一致）。
3. **Run 成功后台**：`Mem0PersistStrategy.persist_turn` → `memory.add(..., user_id=workspace_id, run_id=session_id, infer=True)`。
4. **Celery**（可选）：`agent.memory.compress_mem0` 合并过期/冗余记忆。

### 2.2 Run 主路径（sql）

与现网一致：`AgentMemoryStore` + `invoke_memory_extract` + `memory_persist_service`；不读画像表、无 Celery 压缩、无 mem0 管理端菜单。

---

## 3. 策略接口与目录

### 3.1 Protocol（`backend/app/agent/memory/protocols.py`）

```python
class MemoryRetrieveStrategy(Protocol):
    async def retrieve(
        self, *, workspace_id: UUID, session_id: UUID | None,
        query_text: str, limit: int | None = None,
    ) -> list[MemoryHit]: ...

    async def build_planner_context(
        self, *, workspace_id: UUID, session_id: UUID | None,
        query_text: str, hits: list[MemoryHit],
    ) -> str: ...


class MemoryPersistStrategy(Protocol):
    async def persist_turn(
        self, *, workspace_id: UUID, session_id: UUID, run_id: UUID,
        user_message: str, final_answer: str,
        model: BaseChatModel | None = None,
    ) -> None: ...
```

- `MemoryHit`：保留 `content`, `kind`, `source`, `key`；mem0 路径增加 `score: float | None`、`memory_id: str | None`（mem0 为字符串 ID）。
- **工厂** `memory/factory.py`：`create_memory_strategies() -> tuple[MemoryRetrieveStrategy, MemoryPersistStrategy]`，根据 `settings.agent_memory_backend` 返回成对实现。

### 3.2 目录结构

```
backend/app/agent/memory/
  protocols.py
  factory.py
  hits.py
  sql/
    retrieve.py      # 包装原 memory_store.retrieve + message fallback
    persist.py         # 抽自 memory_persist_service + invoke_memory_extract
  mem0/
    client.py          # Memory.from_config 单例；lifespan 或 lazy init
    retrieve.py
    persist.py
    profile_runtime.py # 现场 session 画像
  profile/
    repository.py
    service.py
```

### 3.3 GraphDeps 变更

- 移除 `memory_store: AgentMemoryStore`。
- 新增 `memory_retrieve: MemoryRetrieveStrategy`、`memory_persist: MemoryPersistStrategy`。
- `AgentGraphRunService` 缓存 `create_memory_strategies()` 结果。

---

## 4. 数据模型

### 4.1 `agent_memory_profile`（主库 `minerva`，无 FK）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | |
| `workspace_id` | UUID, indexed | 必填 |
| `session_id` | UUID, indexed, nullable | NULL = 工作区级；非 NULL = 会话级 |
| `profile_text` | TEXT | 管理端可编辑 |
| `updated_by` | UUID, nullable | Minerva `user_id` |
| `updated_at` | timestamptz | |

- 唯一约束（应用层或部分唯一索引）：`(workspace_id, session_id)` 其中 `session_id` 用 NULLS NOT DISTINCT 或分两条唯一规则（workspace 级 `session_id IS NULL` 一条，会话级一条）。
- **仅 mem0 模式**在 Run 与管理端使用；`sql` 模式不读写。

### 4.2 mem0 外部存储

| 存储 | 说明 |
|------|------|
| `minerva_memory` | mem0 pgvector collection；由 mem0 管理表结构 |
| Neo4j | 实体与关系图；自托管需 APOC |

### 4.3 部署前置

1. PostgreSQL：`CREATE DATABASE minerva_memory;` `\c minerva_memory` `CREATE EXTENSION IF NOT EXISTS vector;`
2. Neo4j：实例 + APOC（自托管）；配置 `MEM0_NEO4J_*`
3. Python：`mem0ai[graph]>=0.1.117`（或经集成测试锁定的版本，需含 pgvector 连接池 per-transaction 修复）

---

## 5. mem0 配置

### 5.1 `Memory.from_config` 示例结构

```python
{
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "dbname": "<minerva_memory>",
            "host": "...", "port": "...", "user": "...", "password": "...",
            "collection_name": "<MEM0_VECTOR_COLLECTION>",
            "embedding_model_dims": <MEM0_EMBEDDING_DIMS>,
            "minconn": <MEM0_PG_POOL_MIN>,
            "maxconn": <MEM0_PG_POOL_MAX>,
        },
    },
    "graph_store": {  # 当 MEM0_GRAPH_ENABLED=true
        "provider": "neo4j",
        "config": {
            "url": "<MEM0_NEO4J_URL>",
            "username": "<MEM0_NEO4J_USERNAME>",
            "password": "<MEM0_NEO4J_PASSWORD>",
            "database": "<MEM0_NEO4J_DATABASE>",
            "base_label": <optional bool>,
        },
    },
    "llm": {
        "provider": "<MEM0_LLM_PROVIDER>",
        "config": { "model": "...", "api_key": "...", "openai_base_url": "..." },
    },
    "embedder": {
        "provider": "<MEM0_EMBEDDER_PROVIDER>",
        "config": { "model": "...", "api_key": "...", ... },
    },
}
```

- 召回：`search(query, user_id=workspace_id, run_id=session_id, limit=...)`；关系增强时 `rerank=True`（与 mem0 文档一致）。
- 写入：`add(messages, user_id=workspace_id, run_id=session_id, infer=True)`。

### 5.2 环境变量清单

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_MEMORY_BACKEND` | `sql` | `sql` \| `mem0` |
| `MEM0_DATABASE_URL` | — | async 不用；供 mem0/psycopg 使用的连接串，库名 `minerva_memory` |
| `MEM0_PG_HOST` / `PORT` / `USER` / `PASSWORD` / `DBNAME` | dbname=`minerva_memory` | 未设 URL 时分项 |
| `MEM0_VECTOR_COLLECTION` | `mem0` | collection 名 |
| `MEM0_EMBEDDING_DIMS` | `1536` | 与 embedder 一致 |
| `MEM0_PG_POOL_MIN` / `MEM0_PG_POOL_MAX` | `1` / `5` | mem0 内置池 |
| `MEM0_GRAPH_ENABLED` | `true` | false 时不配 graph_store |
| `MEM0_NEO4J_URL` | — | 如 `neo4j://127.0.0.1:7687` |
| `MEM0_NEO4J_USERNAME` | `neo4j` | |
| `MEM0_NEO4J_PASSWORD` | — | mem0 且 graph 启用时必填 |
| `MEM0_NEO4J_DATABASE` | `neo4j` | |
| `MEM0_NEO4J_BASE_LABEL` | — | 可选 |
| `MEM0_LLM_PROVIDER` / `MODEL` / `API_KEY` / `BASE_URL` | — | mem0 LLM |
| `MEM0_EMBEDDER_PROVIDER` / `MODEL` / `API_KEY` / `BASE_URL` | — | mem0 Embedder |
| `AGENT_MEMORY_LLM_COMPRESS_ENABLED` | `false` | Run 内对 hits LLM 压缩 |
| `AGENT_MEMORY_PROFILE_LLM_ENABLED` | `false` | 现场 session 画像 LLM 合成 |
| `AGENT_MEMORY_COMPRESS_CELERY_ENABLED` | `false` | 注册 Celery 任务 |
| `AGENT_MEMORY_COMPRESS_CRON` | — | beat cron |
| `AGENT_MEMORY_COMPRESS_MAX_AGE_DAYS` | `90` | 压缩阈值 |
| `AGENT_MEMORY_RETRIEVE_LIMIT` | `20` | 两后端共用 |
| `AGENT_MESSAGE_FALLBACK_LIMIT` | `50` | 仅 sql 路径 |

实现时须同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`。

---

## 6. 画像与压缩

### 6.1 分层画像（mem0）

| 层级 | 来源 | 持久化 |
|------|------|--------|
| 工作区 | `agent_memory_profile`（`session_id IS NULL`） | 是，管理端可编辑 |
| 会话 | `agent_memory_profile`（`session_id` 有值） | 是，管理端可编辑 |
| 运行时 session | `search` + 可选 LLM | **否**（默认） |

`build_planner_context` 拼接顺序建议：持久工作区 → 持久会话 → 运行时 session → 向量 hits 列表。

### 6.2 压缩

| 类型 | 机制 | 默认 |
|------|------|------|
| 写入时 | mem0 `infer=True` 去重/更新 | 开 |
| Run 内 | LLM 压缩召回文本 | **关** |
| Celery | 按年龄/条数合并为摘要记忆，删除细粒度项 | **关**（`AGENT_MEMORY_COMPRESS_CELERY_ENABLED`） |

Celery 任务名：`agent.memory.compress_mem0`；幂等锁 `workspace_id` + `session_id`；使用 **MEM0 LLM** 配置，不用业务 `model_id`。

---

## 7. API 与管理端（mem0 专属）

### 7.1 后端 API（建议前缀 `/workspaces/{workspace_id}/agent/v2/memory`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/profiles` | 列表；query `session_id` 可选 |
| GET | `/profiles/{id}` | 单条 |
| PATCH | `/profiles/{id}` | 编辑 `profile_text` |
| POST | `/profiles` | 新建 workspace/session 画像 |
| DELETE | `/profiles/{id}` | 删除 |
| GET | `/memories` | mem0 `get_all` 分页包装 |
| DELETE | `/memories/{memory_id}` | mem0 `delete` |

- 当 `AGENT_MEMORY_BACKEND=sql` 时上述路由返回 **404** 或 `feature_disabled`（实现时二选一，文档实现对照中固定）。
- GET `/agent/v2/config` 或现有 bootstrap 增加 `memory_backend` 字段，供前端控制菜单显示。

### 7.2 前端

- 工作区 Agent 设置下「记忆管理」：画像编辑 + 记忆列表删除；**仅** `memory_backend === 'mem0'` 显示。
- 破坏性删除使用 **Popconfirm**（仓库约定）。

---

## 8. 错误处理与 SSE

| 场景 | 行为 |
|------|------|
| mem0 retrieve 失败 | `hits=[]`，持久画像仍注入；SSE `degraded=true` |
| mem0 persist 失败 | 不阻断 Run；`memory.persist` 节点 `failed` |
| 现场画像 LLM 失败 | 回退 search 纯文本 |
| `backend=mem0` 配置缺失 | 启动失败 |
| `MEM0_GRAPH_ENABLED=false` | 仅向量路径，不连 Neo4j |

SSE `memory.retrieved` payload 扩展：`backend`, `hit_count`, `profile_layers`, `degraded`。

---

## 9. 测试

| 类型 | 内容 |
|------|------|
| 单元 | factory 返回类型；sql 策略 mock DB |
| 集成 | `@pytest.mark.mem0`：testcontainers PG+vector + Neo4j（可选 job 矩阵分 graph on/off） |
| 回归 | `AGENT_MEMORY_BACKEND=sql` 时 `test_agent_memory_persist_usage` 等不变 |

---

## 10. 实现对照（以代码为准，2026-06-02）

| spec 条目 | 代码位置 | 状态 |
|-----------|----------|------|
| 双策略工厂 | `backend/app/agent/memory/factory.py` | 已实现 |
| Sql retrieve/persist | `backend/app/agent/memory/sql/` | 已实现 |
| Mem0 client / 策略 | `backend/app/agent/memory/mem0/` | 已实现 |
| 画像表 | `backend/sql/patches/2026-06-02-agent-memory-profile.sql` | 已实现 |
| GraphDeps / 节点 | `graphs/deps.py`, `nodes/memory_nodes.py` | 已实现 |
| 管理 API | `backend/app/agent/api/v2/memory_router.py` | 已实现 |
| Celery compress | `backend/app/agent/service/memory_compress_service.py` | 已实现 |
| 前端 | `frontend/src/features/agent/AgentMemoryPage.tsx` | 已实现 |
| 文档 | `docs/agent-module-design.md` §8 | 已回填 |

---

## 11. 非目标（本期不做）

- SQL 与 mem0 双写或混合召回。
- 将 `agent_long_term_memory` 历史数据自动导入 mem0。
- Neo4j 图可视化编辑器（仅可选二期只读预览）。
- mem0 使用 `sys_models` / 工作区模型表作为 LLM 或 Embedding 来源。

---

## 12. Spec 自检（2026-06-02）

- [x] 无 TBD / 占位段落
- [x] 互斥切换、双存储、策略拆分、画像分层、env 清单一致
- [x] 与 minerva 无 FK 约定一致（`agent_memory_profile` 无 REFERENCES）
- [x] 范围可单计划实现；Celery/管理端可分期子任务但属同一 spec
