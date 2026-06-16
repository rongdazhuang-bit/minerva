# 文档分段「先保存再处理」与知识库删除 upload 清理设计

**日期：** 2026-06-16  
**状态：** 已实现（2026-06-16）  
**范围：**  
1. 知识库文档列表 → 分段配置弹窗「保存并处理」  
2. 删除知识库时清理 `dataset_upload_file` 及 S3 对象  

## 背景

### 分段配置「保存并处理」

`DocumentSegmentConfigPanel` 点击「保存并处理」调用 `PATCH .../documents/{id}` 传入 `process_rule`。当前 `update_document` 在**同一事务**内完成：新建 rule → 更新 `dataset_process_rule_id` → `reprocess_document`（删 pgvector、删分段、重置状态）→ `commit` → Celery 入队。

问题：pgvector 删除与 SQL 事务**不同步**。若 `reprocess` 中向量删除成功但 DB `commit` 失败，或 `reprocess` 失败导致整笔回滚，会出现「配置未保存 / 向量已删」等不一致。产品期望：**先持久化文件级分段配置，成功后再触发重新索引**。

### 知识库删除 upload 遗漏

`delete_dataset_cascade` 按设计文档删除 child_chunk、segment、document、process_rule 等，但**未**清理 `dataset_upload_file`。文档通过 `file_id` 与 `data_source_info.upload_file_id` 引用 upload 行；删除知识库后 DB 与 S3 均留下孤儿文件。

## 目标

| # | 目标 |
|---|------|
| 1 | 「保存并处理」分两阶段：阶段 1 保存 `process_rule` 并 commit；阶段 2 再 `reprocess` + 入队 |
| 2 | 阶段 2 失败时配置仍保留（策略 A），明确提示用户并可手动重试重新处理 |
| 3 | 删除知识库时，异步清理本库文档关联的 `dataset_upload_file`、S3 对象及向量 collection |
| 4 | 若 upload 仍被 workspace 内其它文档引用，跳过该 upload，避免误删 |
| 5 | 外部清理（S3 / 向量 / upload 行）失败不阻断 DELETE API，后台尽力执行并记日志 |

## 非目标

- 单文档删除时清理 upload（本次不做）
- 向导未完成 init 产生的孤儿 upload 清理
- 修改 `dataset_upload_file` 表结构（不加 `dataset_id`）
- 修改分段配置弹窗的表单字段或只读展示逻辑

## 方案选择

两项均采用 **方案 A**（后端服务层扩展，不改 API 契约主体）。

### 需求 1：先保存再处理

| 方案 | 说明 | 结论 |
|------|------|------|
| **A** | `update_document` 内两笔事务：保存 commit → reprocess commit + 入队 | **采用** |
| B | 前端 `PATCH` + 新 `POST reprocess` 两次调用 | 边界清晰但需改前端契约 |
| C | 单事务仅调顺序 | 无法解决向量/SQL 不同步 |

### 需求 2：删除 upload + S3 + 向量（异步清理）

| 方案 | 说明 | 结论 |
|------|------|------|
| A | 同步：收集 → 级联删 DB → 删 S3 → 删 upload 行 → 删向量 | S3/向量失败会拖垮 API |
| B | upload 表加 `dataset_id` | 改 schema，与 workspace 级模型不符 |
| **C（采用）** | **同步删核心 DB 行；Celery 异步清理 S3、upload 行、向量 collection** | API 快速返回；外部失败仅记日志 |

**已确认：** S3 失败不影响整体流程；S3、upload 行、向量 collection 均走异步任务，best-effort。

## 需求 1：保存并处理

### 流程

```text
PATCH { process_rule }
  → 阶段 1（事务 1）
      校验：文档存在、非 archived
      新建 DatasetProcessRule
      document.dataset_process_rule_id = new_rule.id
      document.update_at = now
      COMMIT
  → 阶段 2（事务 2，新 session 或显式 begin）
      dataset = require_dataset(...)
      reprocess_document(session, dataset, document)
      COMMIT
      _enqueue_indexing(dataset_id, [document_id])
  → 返回 DatasetDocumentOut（含 reprocess 结果字段）
```

### 失败策略（已确认：策略 A）

| 阶段 | HTTP | 行为 |
|------|------|------|
| 阶段 1 失败 | 4xx | 配置未保存；toast 保存失败 |
| 阶段 2 失败 | **422** | 错误码 `dataset.reprocess_failed_after_save`；配置**已保存**；文档可能仍保留旧分段/向量；响应说明 reprocess 未成功 |

阶段 2 失败时响应体扩展（示例）：

```json
{
  "reprocess_triggered": false,
  "reprocess_error": "重新处理失败，配置已保存。"
}
```

正常成功时 `reprocess_triggered: true`，`reprocess_error: null`。字段挂在 `DatasetDocumentOut` 或通过 wrapper；实现时优先扩展 `DatasetDocumentOut` 可选字段，保持 PATCH 响应模型一致。

### 手动重试端点

新增：

```http
POST /workspaces/{workspace_id}/datasets/{dataset_id}/documents/{document_id}/reprocess
```

- 非 `archived` 文档均可调用（不限于 `indexing_status=error`）
- 逻辑：`reprocess_document` → commit → `_enqueue_indexing`
- 与现有 `POST .../retry` 区分：`retry` 仍仅允许 `error` 状态

阶段 2 失败或用户需再次触发索引时，前端可引导调用 `reprocess`（列表已有重试入口时可复用或链式调用）。

### 前端

`DocumentSegmentConfigPanel`：

- 成功：`reprocess_triggered === true` → 现有「保存成功」toast
- 部分成功：`reprocess_triggered === false` → toast「配置已保存，重新处理失败，请稍后重试」（i18n 新增 key）
- 两种情况下均刷新 document query、更新 `savedSnapshot`（配置已持久化）

### 后端改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/dataset/service/document_service.py` | `update_document` 两阶段；新增 `reprocess_document_for_api` 或复用 `reprocess_document` + 入队 |
| `backend/app/dataset/api/router.py` | 注册 `POST .../reprocess` |
| `backend/app/dataset/api/schemas.py` | `DatasetDocumentOut` 增加 `reprocess_triggered`、`reprocess_error`（Optional） |
| `backend/tests/test_document_segment_config.py` | 两阶段与 reprocess 端点测试 |

### 实现注意

- 阶段 1、2 须使用独立 commit；阶段 2 异常不得 rollback 阶段 1
- 阶段 2 开始前重新 `get_document_for_dataset` 加载最新 `dataset_process_rule_id`
- `_enqueue_indexing` 仅在阶段 2 commit 成功后调用

## 需求 2：删除知识库 — 同步 DB + 异步外部清理

### 总体原则

- **同步（DELETE API）：** 仅删除 PostgreSQL 内与知识库绑定的业务行，保证列表立即不可见。
- **异步（Celery）：** 向量 collection、S3 对象、`dataset_upload_file` 行 — 尽力删除，**单项失败不抛回 API**，记录 `warning`/`exception` 日志。
- Celery 不可用时：API 仍成功删库；清理任务入队失败记日志（与 `_enqueue_indexing` 在 Celery 缺失时的降级策略对齐，不阻断 DELETE）。

### 同步流程（`delete_dataset`）

```text
1. require_dataset
2. SELECT documents WHERE dataset_id = ?
3. 构建 cleanup_manifest（内存，不入库）：
     workspace_id
     dataset_id
     indexing_technique
     uploads: [{ id, storage_key }]  — 见下方收集规则
4. delete_dataset_cascade（仅 SQL，不含向量/upload/S3）：
     child_chunk → segment → document → process_rule → keyword → query → dataset
5. COMMIT
6. enqueue dataset_cleanup_task(cleanup_manifest)
7. 返回 204
```

**upload 收集规则（在删 document 前完成）：**

- 从各 document 取 `file_id`（优先）或 `data_source_info.upload_file_id`
- 加载 `DatasetUploadFile` 行
- 对每个 upload_id：若 workspace 内**其它 dataset** 仍有 document 引用同一 `file_id` → **不写入 manifest**（防误删共享文件）

### 异步流程（Celery `dataset.cleanup`）

任务名：`dataset.cleanup`（常量 `DATASET_CLEANUP_TASK_NAME`）。

```text
对每个 manifest.uploads（幂等、逐项 try/except）：
  1. 再次 COUNT 跨库引用 → 若已被引用则 skip
  2. S3FileService.delete_file(storage_key) — 失败记日志，继续
  3. DELETE dataset_upload_file WHERE id = ? — 失败记日志，继续

向量（try/except）：
  若 indexing_technique == high_quality：
    delete_vector_collection(dataset_id) — 失败记日志

返回 summary：{ s3_deleted, s3_failed, upload_rows_deleted, vector_dropped }
```

任务须**幂等**：对象/行已不存在时视为成功，不抛错。

### 从 `delete_dataset_cascade` 移除的同步步骤

| 原逻辑 | 修订后 |
|--------|--------|
| `delete_vector_collection` 在 cascade 末尾同步调用 | 移至 Celery |
| （计划中的）同步 S3 + upload 行 | 移至 Celery |

### 后端改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/dataset/service/deletion_service.py` | 拆分 `build_dataset_cleanup_manifest`、`delete_dataset_cascade`（纯 SQL） |
| `backend/app/dataset/service/dataset_service.py` | `delete_dataset`：构建 manifest → cascade → commit → enqueue |
| `backend/app/dataset/task/cleanup_task.py` | **新建** Celery 任务 |
| `backend/app/dataset/domain/constants.py` | `DATASET_CLEANUP_TASK_NAME` |
| `backend/app/celery_app.py` | import cleanup_task |
| `backend/tests/test_dataset_delete_upload.py` | API 同步删库 + mock enqueue；任务单测覆盖 S3 失败仍删 upload 行等 |

### 边界

| 场景 | 处理 |
|------|------|
| 文档无 file_id | manifest 不含该项 |
| 同一 upload 被本库多文档引用 | manifest 去重一次 |
| upload 被他库文档引用 | 不进入 manifest |
| S3 对象已不存在 / 删除失败 | 记日志；仍尝试删 upload DB 行 |
| 向量 collection 删除失败 | 记日志；任务仍算完成（可运维手动清理） |
| economy 模式 | manifest 仍含 uploads；跳过向量删除 |
| Celery 未安装/入队失败 | DELETE 已成功；日志告警，upload/S3/向量可能残留 |

### 日志

使用 `get_logger`（见 minerva-conventions）：每项失败 `log.warning` 或 `log.exception`，包含 `dataset_id`、`upload_id`、`storage_key`、异常摘要。

## 测试

### 保存并处理

1. PATCH `process_rule` 成功 → 新 rule 行、`dataset_process_rule_id` 更新、`indexing_status=waiting`、任务入队
2. mock 阶段 2 `delete_vector_nodes` 失败 → rule 已保存、422 + `reprocess_failed_after_save`
3. `POST reprocess` 对非 archived 文档可再次入队
4. archived 文档 PATCH / reprocess → 422
5. 仅 PATCH `name` 不触发 reprocess（回归）

### 删除知识库 upload

1. DELETE API 返回 204，`dataset` 及关联 SQL 行已不存在
2. `dataset.cleanup` 任务被 enqueue，payload 含 2 个 upload
3. 任务内 S3 mock 失败 → upload DB 行仍被删除（或按实现顺序：S3 失败后仍尝试 DB），任务不抛错
4. upload 被另一 dataset 引用 → manifest 不含该 id，任务不删
5. Celery 任务单测：向量删除失败 → 任务完成并记日志

### 删除知识库（API 层）

1. DELETE 后列表不可见（同步 SQL）
2. enqueue 被调用且 manifest 正确

## 文档回填

- 更新 `docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md` §3.3 删除顺序，增加 `dataset_upload_file`（S3 对象同删）
- 更新 `docs/superpowers/specs/2026-06-16-document-segment-config-design.md` §保存流程，注明两阶段实现见本文档

## 验收标准

- [x] 「保存并处理」：配置先 commit，再 reprocess；阶段 2 失败时配置保留且 UI 明确提示
- [x] `POST .../reprocess` 可用且测试覆盖
- [x] 删除知识库：API 同步删 SQL；Celery 异步清理 upload + S3 + 向量
- [x] 跨库共享 upload 不被 manifest 收录
- [x] S3/向量失败不阻断 DELETE API，任务内记日志
- [x] 设计文档 §3.3 与分段配置 spec 已交叉引用

## 相关文档

- `docs/superpowers/specs/2026-06-16-document-segment-config-design.md`
- `docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md`
- `backend/app/translate/service/job_delete.py` — S3 删除与吞异常参考（本设计在 Celery 任务内采用同类 best-effort）
