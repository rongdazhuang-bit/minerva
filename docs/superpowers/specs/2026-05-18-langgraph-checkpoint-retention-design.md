# LangGraph Checkpoint 时间戳与保留清理设计

**日期**：2026-05-18  
**状态**：已实现（2026-05-18）  
**依据**：头脑风暴——为 `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` 增加 `create_at`、`update_at`；`update_at` 由 **`MinervaAsyncPostgresSaver`** UPSERT SQL 维护（无库触发器）；按 `create_at` 可配置保留天数（默认 7 天）分批 DELETE；调度走现有 **`sys_celery` + `MinervaBeatScheduler`**；DDL 写入 **`schema_postgresql.sql`**，存量库幂等变更写入 **`agent_v2_langgraph_migration.sql`**（不新增 `patches/` 文件）。

---

## 1. 背景与目标

- LangGraph `AsyncPostgresSaver`（`langgraph-checkpoint-postgres` ≥3.1）在应用首次启用 checkpoint 时通过 `setup()` 创建 `checkpoints`、`checkpoint_blobs`、`checkpoint_writes` 等表，**官方 DDL 无时间列**，无法按时间做保留与清理。
- **目标**：
  1. 三表增加 `create_at`、`update_at`（`timestamptz NOT NULL DEFAULT now()`），`create_at` 建索引；
  2. `update_at` 在 checkpoints / checkpoint_writes 的 UPSERT 冲突更新时由 `MinervaAsyncPostgresSaver` SQL 设为 `now()`；
  3. `Settings` 可配置保留天数（默认 **7**），Celery 任务按 `create_at < now() - retention` 分批删除；
  4. 周期调度与全站一致：运维在 **`sys_celery`** 配置 cron，Beat 从库加载。

**成功标准**：新库执行 `schema_postgresql.sql` 后表结构含时间列；存量库执行 `agent_v2_langgraph_migration.sql` 后列/索引就绪；应用使用 `MinervaAsyncPostgresSaver`；配置 `sys_celery` 且 Worker 运行后，超保留行被删除且 LangGraph checkpoint 读写不受影响。

---

## 2. 范围与边界

### 2.1 本次范围

- `backend/sql/schema_postgresql.sql`：新增 LangGraph checkpoint 三表 **完整 CREATE**（含官方列 + `create_at` / `update_at` + 索引）。
- `backend/sql/agent_v2_langgraph_migration.sql`：存量库幂等 `ALTER`、回填、索引；`DROP` 历史触发器（若曾部署）。
- `app/config.py`：保留天数、清理开关、批大小。
- Celery：`agent.checkpoint_purge` 任务 + `celery_app` 注册 import。
- 清理服务：同步 SQL 删除 + advisory lock。
- 单元/集成测试（可 `MINERVA_SKIP_DB_TESTS` 跳过 DB）。
- `docs/agent-module-design.md`：Checkpoint 小节补充运维说明。

### 2.2 非本次范围

- 修改 `langgraph-checkpoint-postgres` 包内 `MIGRATIONS`。
- 在 `schema_postgresql.sql` 或迁移中种子插入 `sys_celery` 行（与 `file_ocr.scan_init` 一致，由运维/API 配置；spec 仅提供示例）。
- 按 `thread_id` / `workspace_id` 选择性保留（首期全表统一 cutoff）。
- `checkpoint_migrations` 表结构变更。

---

## 3. 数据库设计

### 3.1 列与索引（三表共性）

| 列 | 类型 | 说明 |
|----|------|------|
| `create_at` | `timestamptz NOT NULL DEFAULT now()` | 行首次插入时间；**清理唯一依据** |
| `update_at` | `timestamptz NOT NULL DEFAULT now()` | 末次 UPDATE 时间（含 UPSERT 更新路径） |

索引（每表）：

- 保留 LangGraph 已有 `thread_id` 索引（`checkpoints_thread_id_idx` 等，名称与官方一致）。
- **新增** `ix_checkpoints_create_at`、`ix_checkpoint_blobs_create_at`、`ix_checkpoint_writes_create_at`（均建在 `create_at`）。

命名与项目 `sys_*` 表一致，使用 **`create_at` / `update_at`**（非 Agent 域的 `created_at` / `updated_at`）。

### 3.2 表结构（与 langgraph-checkpoint-postgres 3.x 对齐）

**`checkpoints`**

```sql
thread_id TEXT NOT NULL,
checkpoint_ns TEXT NOT NULL DEFAULT '',
checkpoint_id TEXT NOT NULL,
parent_checkpoint_id TEXT,
type TEXT,
checkpoint JSONB NOT NULL,
metadata JSONB NOT NULL DEFAULT '{}',
create_at TIMESTAMPTZ NOT NULL DEFAULT now(),
update_at TIMESTAMPTZ NOT NULL DEFAULT now(),
PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
```

**`checkpoint_blobs`**

```sql
thread_id TEXT NOT NULL,
checkpoint_ns TEXT NOT NULL DEFAULT '',
channel TEXT NOT NULL,
version TEXT NOT NULL,
type TEXT NOT NULL,
blob BYTEA,
create_at TIMESTAMPTZ NOT NULL DEFAULT now(),
update_at TIMESTAMPTZ NOT NULL DEFAULT now(),
PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
```

**`checkpoint_writes`**

```sql
thread_id TEXT NOT NULL,
checkpoint_ns TEXT NOT NULL DEFAULT '',
checkpoint_id TEXT NOT NULL,
task_id TEXT NOT NULL,
task_path TEXT NOT NULL DEFAULT '',
idx INTEGER NOT NULL,
channel TEXT NOT NULL,
type TEXT,
blob BYTEA NOT NULL,
create_at TIMESTAMPTZ NOT NULL DEFAULT now(),
update_at TIMESTAMPTZ NOT NULL DEFAULT now(),
PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
```

> `task_path` 为官方 migration 后续追加列；`schema_postgresql.sql` 建表时直接包含，避免与 `setup()` 后结构不一致。

### 3.3 `update_at` 维护（应用代码）

- **`MinervaAsyncPostgresSaver`**（`backend/app/agent/infrastructure/minerva_postgres_saver.py`）子类化 LangGraph `AsyncPostgresSaver`，覆盖 `UPSERT_CHECKPOINTS_SQL` / `UPSERT_CHECKPOINT_WRITES_SQL`，在 `ON CONFLICT DO UPDATE` 子句中增加 `update_at = now()`。
- **`checkpoint_blobs`** 官方为 `ON CONFLICT DO NOTHING`，仅首次 `INSERT` 写入 `update_at`（列默认值）。
- **无** PostgreSQL 触发器；存量库迁移脚本会 `DROP` 已部署的触发器与 `minerva_checkpoint_set_update_at()`（若存在）。

**语义**：

- `INSERT`：`create_at`、`update_at` 均由 `DEFAULT now()` 写入。
- `INSERT … ON CONFLICT DO UPDATE`（checkpoints / writes）：`create_at` 不变；`update_at` 由 UPSERT SQL 刷新。

### 3.4 与 LangGraph `setup()` 的协作

| 场景 | 行为 |
|------|------|
| 新环境先跑 `schema_postgresql.sql` | 表已含时间列；`setup()` 的 `CREATE TABLE IF NOT EXISTS` 跳过 |
| 仅跑过 `setup()` 的旧环境 | 执行 `agent_v2_langgraph_migration.sql` 补列/索引 |
| LangGraph `INSERT` 未列出时间列 | 依赖 `DEFAULT`；兼容 |

**存量回填**（迁移 SQL 内）：对 `create_at IS NULL` 的行（补列后）设 `create_at = now()`, `update_at = now()`，避免迁移后首轮清理误删历史数据。

### 3.5 库级约定

- **不**为三表添加 `FOREIGN KEY`（与 Minerva 全库约定一致）。
- **不**修改 `checkpoint_migrations`。

---

## 4. 清理任务设计

### 4.1 配置项（`app/config.py`）

| 字段 | 环境变量示例 | 默认 | 说明 |
|------|----------------|------|------|
| `agent_langgraph_checkpoint_retention_days` | `AGENT_LANGGRAPH_CHECKPOINT_RETENTION_DAYS` | `7` | 保留天数 |
| `agent_langgraph_checkpoint_cleanup_enabled` | `AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_ENABLED` | `true` | `false` 时任务 no-op |
| `agent_langgraph_checkpoint_cleanup_batch_size` | `AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_BATCH_SIZE` | `1000` | 每表每轮 `DELETE` 上限 |

`agent_langgraph_checkpoint_enabled=false` 时 **仍执行清理**（仅关闭新 checkpoint 写入能力时清理历史数据）。

### 4.2 Celery 任务

| 项 | 值 |
|----|-----|
| 任务全名 | `agent.checkpoint_purge` |
| 模块 | `backend/app/agent/task/checkpoint_purge_job.py`（或同级路径） |
| 常量 | `AGENT_CHECKPOINT_PURGE_TASK_NAME = "agent.checkpoint_purge"` |
| 注册 | `celery_app.py` 中 `import app.agent.task.checkpoint_purge_job` |

**流程**：

1. 若 `cleanup_enabled` 为 false → 返回 `{skipped: true}`。
2. `pg_try_advisory_lock(<固定 int64 key>)`；失败 → 返回 `{skipped: true, reason: "lock"}`（防止多 workspace 各配一条 `sys_celery` 时并发双删）。
3. `cutoff = timezone-aware now() - retention_days`。
4. 按表顺序循环删除至本轮 0 行：  
   **`checkpoint_writes` → `checkpoint_blobs` → `checkpoints`**  
   每表 SQL（示意）：

   ```sql
   DELETE FROM checkpoint_writes
   WHERE ctid IN (
     SELECT ctid FROM checkpoint_writes
     WHERE create_at < %(cutoff)s
     LIMIT %(batch)s
   );
   ```

5. 释放 advisory lock；返回 `{writes, blobs, checkpoints}` 各表删除行数。

**连接**：使用 `settings.sync_database_url`（与 Beat / 其他 sync 任务一致），**不**占用 LangGraph checkpoint 连接池。

### 4.3 `sys_celery` 调度

与 `file_ocr.scan_init` 相同机制，参见 `docs/superpowers/specs/2026-04-30-celery-distributed-scheduler-design.md`。

| 字段 | 建议值 |
|------|--------|
| `task_code` | `agent_checkpoint_purge`（workspace 内唯一） |
| `task` | `agent.checkpoint_purge`（与 `@shared_task(name=...)` 一致） |
| `cron` | 运维配置；建议每天 03:00：`0 0 3 * * *`（6 段，秒 分 时 日 月 周） |
| `timezone` | `Asia/Shanghai`（或与站点一致） |
| `enabled` | `true` |

**运维约定**：

- Checkpoint 数据 **不按 workspace 分表**；全站 **仅需一条** 启用的清理任务（任选 workspace 挂载）。
- 若误配多条，advisory lock 保证同一时刻仅一个实例执行 DELETE。

**示例（勿写入自动迁移，仅供运维参考）**：

```sql
-- INSERT INTO sys_celery (id, workspace_id, name, task_code, cron, task, enabled, ...)
-- VALUES (gen_random_uuid(), '<workspace_uuid>', 'LangGraph Checkpoint 清理', 'agent_checkpoint_purge',
--         '0 0 3 * * *', 'agent.checkpoint_purge', true, ...);
```

任务 **忽略** `sys_celery.args_json` / `kwargs_json`；保留天数只读 `Settings`。

---

## 5. 错误处理与可观测性

- 任务日志：开始/结束、cutoff、各表删除行数、advisory lock 跳过原因。
- SQL 异常：记录后抛出，由 Celery 记录 `last_status` / `last_error`（若 Beat 回写 `sys_celery` 运行态）。
- 单轮批删除控制事务时长，避免长锁表。

---

## 6. 测试策略

- **单元**：cutoff 计算、lock 未获取时短路、批循环终止条件（mock 连接）。
- **集成**（可选）：插入 `create_at` 为昨日/今日 的行，执行 purge 后断言计数；受 `MINERVA_SKIP_DB_TESTS` 控制。
- **回归**：`test_langgraph_checkpointer` 不受影响；迁移 SQL 在 CI 中可文档化手工检查项。

---

## 7. 文档回填

实现完成后更新 `docs/agent-module-design.md` §Checkpoint：

- 时间列与 `MinervaAsyncPostgresSaver` 说明；
- `Settings` 三项；
- `sys_celery` 配置步骤与「单条启用」约定。

---

## 8. 自检记录（spec 发布前）

- [x] 无未决 `TBD`：调度、DDL 位置、回填策略、删除顺序均已明确。
- [x] 与 Minerva 无外键约定一致。
- [x] 与 `langgraph-checkpoint-postgres` 3.x 官方列一致（含 `task_path`）。
- [x] 清理只看 `create_at`；`update_at` 由应用 UPSERT SQL 维护，不参与 cutoff。
- [x] 范围可放入单一实现计划。

---

## 9. 实现对照（以代码为准，2026-05-18）

| 项 | 代码 / SQL |
|----|------------|
| 新库 DDL | `backend/sql/schema_postgresql.sql`（LangGraph checkpoint 段） |
| 存量迁移 | `backend/sql/agent_v2_langgraph_migration.sql` |
| Settings | `backend/app/config.py` |
| 清理服务 | `backend/app/agent/service/checkpoint_purge_service.py` |
| Checkpointer | `backend/app/agent/infrastructure/minerva_postgres_saver.py` |
| 常量 / lock key | `backend/app/agent/constants.py` → `2026051801` |
| Celery 任务 | `backend/app/agent/task/checkpoint_purge_job.py` → `agent.checkpoint_purge` |
| Beat 注册 | `backend/app/celery_app.py` |
| 测试 | `backend/tests/test_checkpoint_purge.py` |
