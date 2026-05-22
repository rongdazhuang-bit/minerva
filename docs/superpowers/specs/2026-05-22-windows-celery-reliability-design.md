# Windows 环境 Celery Worker 可靠性设计

**日期**：2026-05-22  
**状态**：待实现  
**依据**：头脑风暴——Windows 上 Celery Worker 易假死、不消费 `sys_celery` 定时任务与「立即执行」、运行一段时间后退化、`Ctrl+C` 无法干净退出。

---

## 1. 背景与现象

### 1.1 用户侧现象（已确认）

| 维度 | 描述 |
|------|------|
| 启动方式 | `scripts\run-celery.cmd <profile> worker`，**未**设置 `MINERVA_CELERY_USE_PREFORK` |
| 任务类型 | 设置页 **`sys_celery` 定时任务**（非仅文档翻译/OCR 长任务） |
| 表现 | **A** Worker 窗口仍在、日志无明显报错，队列任务不动；**B** 进程已挂或窗口无响应；**D** 启动后数分钟内正常，随后不消费 |
| Beat | **独立终端** Beat 持续运行，到点有调度 |
| 立即执行 | Cron 不跑时，**「立即执行」也不被 Worker 消费** |

### 1.2 推论

- Beat 与 API `enqueue_task`（run-now）均向**同一默认队列**投递；二者同时失效说明问题在 **Worker 消费端或 Broker 连接**，而非 Beat 未发任务。
- 当前 `app/celery_app.py` 在 `win32` 且未开 prefork 时设置 **`worker_pool = "solo"`**（单线程串行）。`.env.example` 注释写「默认 threads / prefork 可选」，与代码不一致，需修正。

### 1.3 目标

1. Windows 开发机上 Worker **长期稳定消费**（含 `sys_celery` 定时与 run-now）。
2. **Ctrl+C** 或配套脚本可可靠结束 Worker/Beat 进程树。
3. 连接空闲断开（如 WinError 10053）后 Worker **自动恢复**或可被运维步骤快速恢复。
4. 文档与 env 示例与实现一致；保留 Linux/macOS 行为不退化。

### 1.4 成功标准

- 使用 `demo.default_job`、1 分钟级 Cron + run-now，连续运行 **≥30 分钟**仍能在 Worker 日志看到 `received` / `demo.default_job start`。
- 模拟 Redis 短暂不可用后恢复，Worker 在 **无需手动杀进程** 的前提下恢复消费（或文档规定的单次重启步骤可恢复）。
- `run-celery.cmd` 窗口 **Ctrl+C** 或 `scripts/stop-celery.cmd` 能在 **10 秒内**结束相关 Python 进程，无残留 `celery.exe` 占端口/队列。

---

## 2. 范围与边界

### 2.1 本次范围

| 项 | 说明 |
|----|------|
| `backend/app/celery_app.py` | Windows 默认 pool、Broker/Worker 连接参数、`MINERVA_CELERY_POOL` |
| `backend/app/config.py` | 新增 pool/concurrency 等 Settings（若采用配置化） |
| `backend/.env.example`、`backend/.env.dev` | 同步新变量与注释 |
| `scripts/run-celery.cmd` / `.sh` | 显式 `--pool`、`--concurrency`；可选优雅停止说明 |
| `scripts/stop-celery.cmd`（新建） | Windows 结束当前目录下 Celery 进程树 |
| `README.md` / `README.en.md` | Windows Celery 排错与双终端要求 |
| `.cursor/skills/minerva-conventions/SKILL.md` | §3 脚本列表、env 变量说明（若新增） |

### 2.2 非本次范围

- 将 Celery **强制**迁入 Docker/WSL（仅 README **推荐**为可选方案）。
- 重写 `MinervaBeatScheduler` 或 `sys_celery` CRUD。
- 恢复已删除的 pytest 套件（验证以手工清单为准）。
- 生产环境 systemd/supervisor 编排。

---

## 3. 根因假设（实现时按优先级验证）

| 优先级 | 假设 | 验证方式 |
|--------|------|----------|
| P1 | Kombu/Redis **长连接空闲断开**，Consumer 假活不再 `brpop` | Worker debug 日志；Redis `CLIENT LIST`；断网恢复试验 |
| P2 | **solo** 池内单任务**挂死**（同步 DB/Redis/子进程），阻塞后续所有消息 | 卡住时看是否有一条任务 `start` 无 `finish` |
| P3 | Windows **信号处理**差，进程僵死；Ctrl+C 未传到 Celery | 任务管理器进程树；stop 脚本清树 |
| P4 | `scheduled_singleton_guard` 锁未释放导致**跳过** | 日志 `already_running`；Redis `KEYS minerva:celery:scheduled_singleton:*` |
| P5 | Broker URL/队列不一致 | 对比 Beat、API、Worker 的 `CELERY_BROKER_URL` 与 `CELERY_DEFAULT_QUEUE` |

---

## 4. 方案选型

### 4.1 候选方案

| 方案 | 概要 | 优点 | 缺点 |
|------|------|------|------|
| A | Celery 仅在 WSL2/Docker/Linux 跑 | 最稳、与生产一致 | 本地多一套环境 |
| B | **Windows 原生加固**（推荐） | 保留双 cmd 习惯；针对 P1–P3 | threads 对 CPU 密集有限 |
| C | 仅文档/运维清单 | 零代码 | 不解决 D 类退化 |

### 4.2 结论

采用 **方案 B** 为必做；**方案 A** 写入 README 作为团队可选标准；**方案 C** 作为 B 的运维附录。

---

## 5. 运行时设计

### 5.1 Worker Pool（Windows）

| 平台 | 默认 `worker_pool` | 说明 |
|------|-------------------|------|
| `win32` | **`threads`** | 避免 billiard prefork 的 `trace._localized` 问题；允许定时任务与 run-now 并行排队执行（受 GIL 约束，适合 I/O 型任务） |
| 其它 | `prefork`（Celery CLI 默认，或由 conf 覆盖） | 保持现有 Linux 行为 |

**环境变量**（替代仅控制 prefork 的 `MINERVA_CELERY_USE_PREFORK`）：

| 变量 | 取值 | 默认（Windows） |
|------|------|-----------------|
| `MINERVA_CELERY_POOL` | `threads` \| `solo` \| `prefork` | `threads` |
| `MINERVA_CELERY_CONCURRENCY` | 正整数 | `4`（仅 threads/prefork 生效） |

**兼容**：`MINERVA_CELERY_USE_PREFORK=1` 在 Windows 上等价于 `MINERVA_CELERY_POOL=prefork`；保留 `worker_process_init` 补丁。

**任务线程安全**：`demo.default_job`、checkpoint purge、file_ocr scan、translate pipeline 以 DB/HTTP 为主，默认可在 threads 下运行；若发现非线程安全状态，在任务级文档注明并回退 `solo` 做排查。

### 5.2 Broker / Consumer 可靠性

在 `celery_app.conf.update(...)` 中补充（具体键名以实现时 Celery 5.x 文档为准）：

- `broker_heartbeat`：建议 **30** 秒级，降低空闲断连。
- 沿用现有 `broker_connection_retry`、`broker_connection_retry_on_startup`、`broker_transport_options`（含 `socket_keepalive`、`health_check_interval`）。
- `worker_cancel_long_running_tasks_on_connection_loss`：**True**（连接丢失时取消长任务，避免 solo/threads 永久占坑）。
- 视需要设置 `broker_pool_limit` / Redis transport 超时与现有 `celery_redis_socket_*` 对齐。

Beat **不**改 pool；Beat 进程仅调度，继续独立终端运行。

### 5.3 定时任务单例锁

保持 `scheduled_singleton_guard` 逻辑；补充：

- 锁 key 前缀：`minerva:celery:scheduled_singleton:`（已有）。
- TTL 由 `CELERY_SCHEDULED_TASK_LOCK_TTL_SECONDS` 控制；任务异常退出依赖 TTL 过期释放。
- **运维**：卡住且日志大量 `already_running` 时，删除对应 Redis key 后重试 run-now。

---

## 6. 启动脚本与优雅退出

### 6.1 `run-celery`

- Worker 子命令增加：
  - `--pool=<MINERVA_CELERY_POOL>`（Windows 默认 `threads`）
  - `--concurrency=<MINERVA_CELERY_CONCURRENCY>`（pool 支持时）
- Beat 子命令不变。
- 注释说明：**必须** Worker、Beat 各一终端；Windows 推荐 `threads`。

### 6.2 `stop-celery.cmd`（新建）

- 用法：`scripts\stop-celery.cmd`（可选 profile 过滤，首版可结束所有 `celery.exe` / 匹配 `app.celery_app` 的 python 子进程）。
- 实现：`taskkill /F /T /IM celery.exe` 与/或按窗口标题、命令行包含 `celery -A app.celery_app` 的 Python 进程树。
- README 说明：当 **Ctrl+C 无效** 时优先使用本脚本。

### 6.3 Linux/macOS

- `run-celery.sh` 同步 `--pool` / `--concurrency` 环境变量传递。
- 可选 `stop-celery.sh` 使用 `pkill -f "celery -A app.celery_app"`（非必须，可作为对称实现）。

---

## 7. 可观测与排错手册（README 章节）

### 7.1 日常检查清单

1. Redis 可达：`python -m app.sys.celery.service.broker_preflight`（启动脚本已调用）。
2. 两个终端：Beat 日志含 `Scheduler: Sending due task`；Worker 含 `ready` / `received`。
3. 队列深度：`redis-cli LLEN <CELERY_DEFAULT_QUEUE>`（默认 `celery`）是否持续增长。
4. 单例锁：`KEYS minerva:celery:scheduled_singleton:*` 是否异常堆积。

### 7.2 推荐可选方案（WSL2/Docker）

- 在 Linux 侧运行 `run-celery.sh`，Windows 仅跑 API + 前端；Broker 使用 Windows 本机 Redis 时绑定 `0.0.0.0` 并配置 URL 为宿主机 IP。

---

## 8. 配置与文档同步

| 文件 | 变更 |
|------|------|
| `backend/app/config.py` | 可选：`celery_worker_pool`、`celery_worker_concurrency` 映射 env |
| `backend/.env.example` | 删除错误 prefork/threads 注释；增加 `MINERVA_CELERY_POOL`、`MINERVA_CELERY_CONCURRENCY` |
| `backend/.env.dev` | 与 example 同步（若团队有非默认值） |
| `minerva-conventions` §3 | 增加 `stop-celery.cmd`、新 env 变量 |

---

## 9. 手工验证计划

1. **基线**：`demo.default_job` + 每分钟 Cron，Worker `threads` pool，观察 30 分钟。
2. **run-now**：Worker 假死后点击立即执行，修复后应秒级 `received`。
3. **断 Redis**：停 Redis 30s 再启，确认 Worker 恢复或按文档重启一次即可。
4. **退出**：Ctrl+C 与 `stop-celery.cmd` 各测一次，无残留进程。
5. **回退**：`MINERVA_CELERY_POOL=solo` 复现旧行为，确认文档说明差异。

---

## 10. 实现对照（待填）

| 项 | 状态 |
|----|------|
| `celery_app.py` pool 默认与 conf | 待实现 |
| `config.py` + `.env.*` | 待实现 |
| `run-celery.*` CLI 参数 | 待实现 |
| `stop-celery.cmd` | 待实现 |
| README 排错章节 | 待实现 |
| `minerva-conventions` 更新 | 待实现 |

---

## 11. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 初稿：头脑风暴结论与用户确认（方案 B + 现象 A/B/D、任务类型 C、启动 A、Beat+run-now 均失败） |
