# 文件 OCR：`INIT` 任务 Celery 周期扫描与策略化解析设计

**日期**：2026-05-13  
**状态**：已确认（用户）  
**依据**：头脑风暴结论——采用 **Celery 周期任务**；`ocr_type` 与设置页统一为 **`PADDLE_OCR` / `MINERU`**；结果表 DDL 已存在于 `backend/sql/schema_postgresql.sql`（`ocr_file_paddleocr`、`ocr_file_mineru`）；**首期实现 PaddleOCR 全流程**，**MinerU 仅占位（策略注册 + 不进入扫描队列）**。

---

## 1. 背景与目标

- 当前 `ocr_file` 在创建任务后处于 `INIT`，尚无后台消费流程将源文件送入 OCR 引擎并落库结果表。
- 目标：在 **`app/file_ocr`** 垂直模块内增加 **Celery 定时扫描**，按 `ocr_type` **策略化**调用不同解析路径；解析结果写入 **`ocr_file_paddleocr`** 或（二期）**`ocr_file_mineru`**，并维护主表 **`ocr_file`** 状态与页数。
- 调度方式与全站一致：任务由 **Celery Worker** 执行，触发节奏由 **`sys_celery` + Beat**（`MinervaBeatScheduler`）管理，参见 `docs/superpowers/specs/2026-04-30-celery-distributed-scheduler-design.md`。

---

## 2. 范围与边界

### 2.1 本次范围

- 新增 Celery 共享任务（建议命名如 **`file_ocr.scan_init`**），周期由运维/产品在 **`sys_celery`** 中配置（或由种子数据提供一条默认 cron，具体在实现计划中定）。
- 扫描并处理 **`ocr_file.status = 'INIT'`** 且 **`ocr_file.ocr_type` 属于首期支持集合** 的记录（见 3.2）。
- **策略模式**：按 `ocr_type` 分发到具体策略实现；策略负责「选工具 → 取源文件 → 调 HTTP → 写结果表 → 更新主表」。
- 新增 ORM：**`OcrFilePaddleocr`**、**`OcrFileMineru`**（与现有 DDL 字段对齐）。
- **数据与 API 统一**：将历史/代码中的 **`MINER_U` 全部改为 `MINERU`**（含 DB 一次性更新、Pydantic、前端、测试）。

### 2.2 非本次范围（首期）

- **MinerU 实际解析与写 `ocr_file_mineru`**：仅保留 **策略占位类** 与注册表项；**扫描 SQL 不包含 `MINERU`**，避免 `INIT` 任务被反复空转或误标失败。
- 结果表 **`file_id` 外键**：DDL 当前未声明 FK；首期可不强制迁移，仅在实现阶段 **可选** 补充 `REFERENCES ocr_file(id)` 以加强完整性（若加迁移需评估线上数据）。
- 高级任务编排（优先级队列、DAG、多阶段流水线）不在本次范围。

---

## 3. 需求冻结

### 3.1 `ocr_type` 权威取值

与设置页（`MINERU_OCR_TYPE_CODE` / `PADDLE_OCR_TYPE_CODE`）一致：

| 值 | 说明 |
|----|------|
| `PADDLE_OCR` | Paddle 系引擎；首期 **完整实现**。 |
| `MINERU` | MinerU；首期 **仅占位**，不参与扫描消费。 |

**迁移**：对已有 `ocr_file.ocr_type = 'MINER_U'` 的行执行 `UPDATE` 为 `'MINERU'`（迁移脚本或 SQL 补丁，与代码发布顺序在实现计划中约定：先迁移后发版或兼容读取二选一，**禁止**长期双写法）。

### 3.2 首期扫描支持集合

- **`supported_ocr_types = {'PADDLE_OCR'}`**。
- 查询条件示例语义：`WHERE status = 'INIT' AND ocr_type IN ('PADDLE_OCR')`，并配合行级锁（见 4.3）。

### 3.3 结果表字段（与 DDL 对齐）

**`ocr_file_paddleocr`**：`id`, `workspace_id`, `file_id`, `page_index`, `markdown_text`, `markdown_images`, `create_at`, `update_at`。

**`ocr_file_mineru`**：字段集合与上表等价（列顺序在 DDL 中已定义）；二期策略写入。

### 3.4 主表状态机

| 转移 | 条件 |
|------|------|
| `INIT` → `PROCESS` | 工作进程 **成功认领** 该条（见 4.3）。 |
| `PROCESS` → `SUCCESS` | 策略完成 HTTP 调用且结果持久化成功；`page_count` 与结果一致（若服务返回多页，则 `page_count` 为页数；若仅单行汇总，则与产品约定在实现阶段写死规则）。 |
| `PROCESS` → `FAILED` | 无可用 `sys_ocr_tool`、S3 拉取失败、HTTP/业务错误、不可恢复异常；`remark` 写入截断后的错误说明（长度上限与现有字段一致）。 |

不重入 `INIT`（失败由人工「重试」接口或后续 Story 处理；若已有重试 API，扫描器只消费 `INIT`）。

### 3.5 `sys_ocr_tool` 选择规则

- 作用域：与 `ocr_file.workspace_id` 相同的工作空间。
- 过滤：`sys_ocr_tool.ocr_type` 与当前任务 `ocr_file.ocr_type` 一致（首期即 `PADDLE_OCR`）。
- **多条命中**：取 **`update_at` 最大** 的一条作为默认工具；若无 `update_at`，则退化为 **`create_at` 最大**（实现时二选一写死并加单元测试）。
- **零条**：认领后置 `FAILED`，`remark` 标明无可用工具。

---

## 4. 架构与组件

### 4.1 模块布局（建议）

| 路径 | 职责 |
|------|------|
| `app/file_ocr/task/`（或 `tasks/`） | Celery **`@shared_task`** 入口：组装日志、调用扫描服务一次。 |
| `app/file_ocr/service/`（或 `service/scan_init.py`） | **扫描编排**：开 DB 会话、批量拉取、循环调用策略、提交事务边界。 |
| `app/file_ocr/service/strategies/` | **`FileOcrEngineStrategy`** 协议/ABC + `PaddleOcrFileStrategy` + `MineruFileStrategy`（占位）。 |
| `app/file_ocr/domain/db/models.py`（或拆分 `models_result.py`） | `OcrFilePaddleocr`、`OcrFileMineru` ORM。 |

保持与现有 `file_ocr/api`、`file_ocr/domain/db` 分层一致，**不**把业务写进 `sys/celery` 包内（仅注册任务名到 `sys_celery.task` 字段）。

### 4.2 策略接口（概念）

- **注册表**：`Mapping[str, FileOcrEngineStrategy]`，key 为 `PADDLE_OCR`、`MINERU`。
- **方法**（示意）：`async def process(self, *, session, ocr_file: OcrFile, tool: SysOcrTool) -> None`  
  - 策略内部：S3 下载、`ocr_config` 与 `SysOcrTool` 鉴权映射、调用 HTTP 客户端、插入结果行、更新 `ocr_file`。
- **Paddle HTTP 客户端**：优先复用 `app/ocr/paddleocr/` 已设计的能力（见 `docs/superpowers/specs/2026-05-08-paddleocr-vl-api-client-design.md`）；**策略层**负责从 `SysOcrTool` 组装 `LayoutParsingRequest`（含 `file` Base64 或 URL 方案在实现时按部署约定二选一并写入实现计划）。

### 4.3 并发与认领（多 Worker）

- 同一任务 **禁止** 被两个 Worker 同时处理。
- 使用 PostgreSQL **`FOR UPDATE SKIP LOCKED`**：在事务中 `SELECT id ... WHERE status='INIT' AND ocr_type IN (...)` 加锁跳过已锁行，或使用 `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *` 原子认领。
- 每 tick 处理 **批量上限**（配置常量，建议默认 10～50），防止单次任务过长阻塞 Beat 心跳；具体默认值在实现计划中给出。

### 4.4 Worker 内数据库访问

- API 进程使用 `AsyncSession`；Celery 任务为同步入口时，采用项目既有惯例：**`asyncio.run`** 驱动协程主流程，会话来自 **`async_session_factory`**（与 `app/core/infrastructure/db/session.py` 一致），避免在 Worker 中混用未经验证的同步引擎，除非后续统一规范另有要求。

### 4.5 S3 源文件读取

- 复用 **`S3FileService`**（`get_download_proxy` / gateway）在异步上下文中读取 `object_key`，得到字节流或完整 `bytes` 后交给 Paddle 请求体字段（与 Paddle 文档一致：`file` 为 Base64 或 URL）。

---

## 5. Celery 集成

- **任务注册**：`@shared_task(name="file_ocr.scan_init", bind=True)`（名称以最终实现为准，须与 `sys_celery.task` 字符串一致）。
- **调度**：在目标工作空间的 **`sys_celery`** 中新增一条记录：`task` 指向上述全名，`cron` 由运维配置；依赖现有 Beat 从 DB 加载与 Redis 热更新机制。
- **幂等**：单条 `ocr_file` 在 `PROCESS` 或终态时不应再次被扫描选中；若策略写结果表前崩溃，需依赖 **认领 + 重试策略**（可选：超时后由运维或后续「卡住 PROCESS 回收」Story 处理；**首期**可在 spec 中记录为已知限制，或在实现计划中增加「PROCESS 超过 N 分钟回滚为 INIT」的简易守护——**默认不做**，避免 scope 膨胀）。

---

## 6. 错误处理与可观测性

- 日志：任务开始/结束、认领条数、每条 `ocr_file.id` 成功/失败原因摘要（避免打印完整 Base64）。
- HTTP 错误：映射为 `FAILED` + `remark`；可配置重试（若采用 Celery `autoretry_for`，需在实现计划中列出异常类型与最大次数）。
- 无工具 / 无策略：明确错误码或固定 `remark` 前缀，便于前端与运维检索。

---

## 7. 测试策略

- **单元测试**：工具选择（多条 `sys_ocr_tool` 取最新）、`supported_ocr_types` 过滤、`MINERU` 不被扫描。
- **集成测试**：插入 `INIT` + `PADDLE_OCR` + mock `SysOcrTool` + mock S3 + mock httpx，断言 `ocr_file_paddleocr` 行数与 `ocr_file.status`。
- **回归**：更新 `file_ocr` API 测试中 `ocr_type` 字面量为 `MINERU`。

---

## 8. 自检记录（spec 发布前）

- [x] 无未决 `TBD`：PROCESS 悬挂处理明确为「首期默认不自动回收，可选后续 Story」。
- [x] 与 `2026-05-08-paddleocr-vl-api-client-design.md` 边界一致：策略层组装请求，客户端模块不读 DB。
- [x] `MINERU` 占位与「不扫描」无矛盾。
- [x] 范围可放入单一实现计划，无需再拆子系统 spec。

---

## 9. 后续工作（不在本 spec 内展开）

- 启用 **`MINERU` 扫描**：将 `MINERU` 纳入 `supported_ocr_types`，实现 `MineruFileStrategy` 并写 `ocr_file_mineru`。
- 可选：为 `ocr_file_paddleocr.file_id` / `ocr_file_mineru.file_id` 增加外键与级联策略。
