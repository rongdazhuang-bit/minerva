# 分布式定时任务调度设计（Celery + Beat）

## 1. 背景与目标

当前系统仅存在 `sys_celery` 数据表，后端尚未落地 Celery/Beat 调度模块，前端 `scheduler` 仍为占位页面。  
本次目标是在最新 Celery（含 Beat）基础上实现可用的分布式定时任务调度能力，并满足以下要求：

- 服务启动时从 `sys_celery` 加载定时任务配置；
- 任务 CRUD 后实时自动热更新到 Beat；
- 列表操作列支持：编辑、删除、立即执行、停止（含启用恢复）；
- 按工作空间执行：同一任务定义在不同 `workspace` 各自生效；
- 新增/编辑页面内支持 Cron 表达式生成器。

## 2. 范围与边界

### 2.1 本次范围

- 后端新增 `backend/app/sys/celery` 模块，提供任务管理 API 与调度同步服务。
- 补充 `sys_celery` 表字段以支持热更新、执行态可观测与参数化任务。
- 集成 Celery Worker + Beat，采用“DB 真源 + Redis 失效通知”同步机制。
- 前端新增 `minerva-ui/src/features/settings/celery` 管理页面与 Cron 生成器。

### 2.2 非本次范围

- 不引入 RedBeat 或其他第三方 Beat 存储。
- 不做软删除（删除即物理删除）。
- 不做跨工作空间共享任务模板体系。
- 不做任务执行日志大盘与高级告警编排（仅保留必要执行状态字段）。

## 3. 方案选型结论

本次采用 **方案 B：DB 为真源 + Redis 失效通知**。

原因：

- 满足“启动加载 + CRUD 实时热更新”双要求；
- 相比纯轮询，实时性更好且 DB 压力可控；
- 相比 RedBeat 双存储方案，一致性与维护成本更低。

## 4. 数据模型设计（`sys_celery`）

## 4.1 现状评估

现有字段：

- `id`
- `workspace_id`
- `name`
- `cron`
- `status`
- `task`
- `remark`
- `create_at`
- `update_at`

结论：字段不足，无法完整支撑参数化任务、热更新版本控制、执行态展示与可控启停。

## 4.2 字段调整建议

保留现有字段并补充以下字段（分阶段迁移，先兼容后收敛）：

- `task_code VARCHAR(64) NOT NULL`：任务编码（工作空间内可读且稳定标识）。
- `args_json JSONB NULL`：任务位置参数。
- `kwargs_json JSONB NULL`：任务命名参数。
- `timezone VARCHAR(64) NULL DEFAULT 'Asia/Shanghai'`：任务级时区。
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`：启停状态（建议替代 `status`）。
- `next_run_at TIMESTAMPTZ NULL`：下一次计划执行时间（用于列表展示）。
- `last_run_at TIMESTAMPTZ NULL`：最近执行时间。
- `last_status VARCHAR(16) NULL`：最近执行状态（如 `SUCCESS`、`FAILURE`）。
- `last_error TEXT NULL`：最近错误摘要。
- `version BIGINT NOT NULL DEFAULT 0`：调度版本号（热更新核心字段）。

兼容性建议：

- `task` 建议收紧为 `NOT NULL`。
- `status` 可保留一段过渡期，最终由 `enabled` 统一语义。

## 4.3 约束与索引建议

- 唯一约束：`UNIQUE (workspace_id, task_code)`。
- 索引：`(workspace_id, enabled)`。
- 索引：`(enabled, update_at)`。
- 兼容阶段可额外保留 `(workspace_id, status)` 索引。

## 5. 后端架构设计（`backend/app/sys/celery`）

## 5.1 模块目录

- `api/router.py`：路由定义。
- `api/schemas.py`：请求/响应模型。
- `domain/db/models.py`：`SysCelery` ORM 模型。
- `infrastructure/repository.py`：数据库读写封装。
- `service/celery_schedule_service.py`：任务管理业务逻辑（CRUD/立即执行/启停）。
- `service/beat_sync_service.py`：版本发布、Redis 通知、Beat 增量同步。

## 5.2 API 设计

按工作空间隔离：

- `GET /workspaces/{workspace_id}/celery-jobs`：任务列表（分页）。
- `POST /workspaces/{workspace_id}/celery-jobs`：新增任务。
- `PATCH /workspaces/{workspace_id}/celery-jobs/{job_id}`：编辑任务。
- `DELETE /workspaces/{workspace_id}/celery-jobs/{job_id}`：物理删除任务。
- `POST /workspaces/{workspace_id}/celery-jobs/{job_id}/run-now`：立即执行一次。
- `POST /workspaces/{workspace_id}/celery-jobs/{job_id}/stop`：停止任务（`enabled=false`）。
- `POST /workspaces/{workspace_id}/celery-jobs/{job_id}/start`：启用任务（`enabled=true`）。

分页规则：

- 后端默认 `page_size=10`（对齐 `backend/app/pagination.py`）。

## 5.3 调度加载与热更新流程

### 启动加载

1. Beat 启动时查询 `enabled=true` 的任务。
2. 将记录转为 Celery `crontab` 调度项，写入内存调度表。
3. 调度键建议：`{workspace_id}:{task_code}`，确保多工作空间互不覆盖。

### CRUD 热更新

1. 管理端执行新增/编辑/删除/启停并成功提交事务。
2. 对受影响任务执行 `version = version + 1`。
3. 发布 Redis 通知（包含 `workspace_id`、`job_id`、`op`、`version`）。
4. Beat 订阅通知并做增量更新：
   - 新增/启用：写入或覆盖对应调度键；
   - 编辑：替换原调度配置；
   - 停止/删除：移除对应调度键。

### 兜底一致性

- Beat 每 60 秒执行低频版本对账，防止通知丢失导致漂移。

## 5.4 并发与幂等策略

- 所有更新操作均按 `workspace_id + job_id` 精确定位。
- Beat 仅接受不小于本地已应用版本的更新事件。
- 重复通知按 `version` 幂等处理，不重复变更。
- `run-now` 只触发一次性执行，不改动周期配置与 `enabled` 状态。

## 6. 前端页面设计（`features/settings/celery`）

## 6.1 目录结构

- `CeleryPage.tsx`：列表页。
- `CeleryFormModal.tsx`：新增/编辑弹窗。
- `CronBuilder.tsx`：Cron 可视化生成组件。
- `api.ts`：接口请求封装。
- `types.ts`：类型定义。
- `index.ts`：统一导出。

## 6.2 列表页设计

字段列：

- 名称
- 任务编码（`task_code`）
- 任务函数（`task`）
- Cron
- 状态（`enabled`）
- 下次执行时间（`next_run_at`）
- 最近执行时间（`last_run_at`）
- 最近执行状态（`last_status`）
- 备注
- 操作列

操作列：

- 编辑
- 删除（物理删除，强确认）
- 立即执行（二次确认）
- 停止/启用（按当前状态切换）

分页规则：

- 默认每页 `10` 条（对齐 `minerva-ui/src/constants/pagination.ts`）。

## 6.3 新增/编辑表单设计

字段：

- `name`
- `task_code`
- `task`
- `cron`
- `timezone`
- `enabled`
- `args_json`
- `kwargs_json`
- `remark`

交互要点：

- 文本输入与选择器使用 `allowClear`。
- `args_json/kwargs_json` 在提交前做 JSON 合法性校验。
- `cron` 支持“手填 + 生成器”双模式，生成器变更实时回填输入框。
- 提供 Cron 人类可读预览（降低表达式误配）。

## 7. Cron 生成器设计要点

- 支持常见模板：每分钟、每小时、每天、每周、每月、自定义。
- 根据选择维度动态拼装 Cron 字段并即时展示结果。
- 对非法表达式给出明确错误提示，禁止提交。
- 支持“回填编辑”：打开编辑弹窗时可从已有 Cron 反显到生成器（至少支持常见模板反解）。

## 8. 错误处理与可观测性

- 新增/编辑失败：返回字段级错误信息，前端就地提示。
- 热更新通知失败：记录错误日志，依赖 Beat 低频对账恢复一致性。
- 立即执行失败：返回失败原因并写入 `last_error`。
- 任务执行结果由 Worker 回写 `last_run_at/last_status/last_error`，并刷新 `next_run_at`。

## 9. 测试与验收

## 9.1 后端测试

- 启动加载：仅加载 `enabled=true` 且 `workspace_id` 匹配任务。
- CRUD 热更新：新增/编辑/停止/删除后 Beat 在可接受时延内生效。
- 并发更新：高频编辑同一任务时最终版本一致。
- 立即执行：可独立触发且不影响周期调度。

## 9.2 前端测试

- 列表分页、筛选、状态切换与操作列行为正确。
- 新增/编辑表单 JSON 校验、Cron 校验与提交链路正确。
- Cron 生成器模板与自定义模式切换正确，回填行为可用。

## 9.3 验收标准

- 服务启动后可从 `sys_celery` 自动加载任务。
- 任务 CRUD 可实时热更新，无需重启服务。
- 操作列具备编辑、删除、立即执行、停止/启用能力。
- 按工作空间执行语义生效，同任务在不同工作空间互不干扰。
- 前端新增/编辑支持 Cron 生成器，表达式可预览、可校验、可提交。
