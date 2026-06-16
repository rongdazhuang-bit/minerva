# 创建知识库 — 每文档独立 process_rule 行设计

**日期：** 2026-06-16  
**状态：** 待审阅  
**范围：** 新建知识库向导后端 `init_dataset_with_documents`；不含历史数据迁移

## 背景

创建知识库时，用户在向导 Step 2 提交一份整批共用的 `process_rule`。当前 `init_dataset_with_documents` 只插入 **一条** `dataset_process_rule`，所有 `dataset_document` 共用同一 `dataset_process_rule_id`。

「添加文档」流程（`append_documents` + `process_rule`）已约定：**UI 一套配置，DB 每个新文档各绑定独立 `DatasetProcessRule` 行（内容相同）**（见 `2026-06-16-document-append-chunking-design.md` 需求 #5）。

文档分段配置弹窗按 `dataset_document.dataset_process_rule_id` 加载文档级规则；多文档共享同一 rule id 时，后续无法独立修改单文档分段配置。

## 目标

新建知识库时：若一次提交 N 个文件，则 `dataset_process_rule` 表应有 **N 条记录**，`mode` 与 `rules`（JSON 序列化内容）相同，每条记录 `id` 不同，分别绑定到对应 `dataset_document.dataset_process_rule_id`。

## 非目标

- 不迁移历史上已创建、多文档共用同一 `dataset_process_rule_id` 的知识库
- 不修改 API 请求/响应契约
- 不修改前端创建向导 UI 或提交 payload 结构
- 不修改数据库 schema

## 方案选择

采用 **方案 A**：在 `init_dataset_with_documents` 的文件循环内，为每个文档各插入一条 `DatasetProcessRule`，与 `append_documents` 行为对齐。

| 方案 | 说明 | 结论 |
|------|------|------|
| A | 循环内每文档 INSERT 一条 rule | **采用** |
| B | 先插 1 条再批量 clone | 与 append 分叉，无收益 |
| C | 创建后异步补写 rule 行 | 存在不一致窗口，不采用 |

## 行为变更

| | 变更前 | 变更后 |
|---|--------|--------|
| rule 行数 | N 文件 → 1 条 | N 文件 → N 条 |
| `rules` 内容 | 单条 | 各条相同（同一 `rule_payload` 序列化） |
| `dataset_process_rule_id` | 全部相同 | 每文档独立 |
| API | 一份 `process_rule` | 不变 |

## 后端实现

### 主改动：`backend/app/dataset/service/init_service.py`

1. 删除循环外单次 `DatasetProcessRule` 创建。
2. 在 `for position, upload_id in enumerate(file_ids, start=1)` 内：
   - 新建 `DatasetProcessRule`（`dataset_id`、`mode`、`rules=serialize_process_rule(rule_payload)`、`created_by`）
   - `session.flush()` 取得 `rule_id`
   - 创建 `DatasetDocument` 时设置 `dataset_process_rule_id=rule_id`

### 可选重构

从 `document_service.append_documents` 抽出共享 helper，例如：

```python
def _create_process_rule_row(
    session, *, dataset_id, user_id, rule_payload: dict
) -> uuid.UUID:
    ...
```

`init_service` 与 `document_service` 共用，避免重复逻辑。

### 不受影响

| 模块 | 说明 |
|------|------|
| `get_latest_process_rule` | 仍取 dataset 最新 rule 行，用于知识库详情默认展示 |
| Celery 索引任务 | 仍经 `document.dataset_process_rule_id` 加载规则 |
| `PATCH` 文档/知识库 `process_rule` | 行为不变 |
| 历史数据 | 保持原样 |

## 错误处理

与 `append_documents` 一致：任一 `upload_id` 校验失败则整笔事务回滚，不出现部分文档有 rule、部分无 rule 的状态。

## 测试

新增 `backend/tests/test_dataset_init_process_rule.py`：

1. 使用 2 个有效 `file_ids` 调用 `init_dataset_with_documents`
2. 断言 `dataset_process_rule` 行数为 2
3. 断言两行 `rules` 反序列化后内容相同
4. 断言两个 `dataset_document.dataset_process_rule_id` 互不相同且分别指向对应 rule 行

## 验收标准

- [ ] 新建知识库上传 2+ 文件：`dataset_process_rule` 行数 = 文件数
- [ ] 各 rule 行 `mode`、`rules` 内容一致
- [ ] 各 `dataset_document` 绑定不同 `dataset_process_rule_id`
- [ ] 索引任务正常完成
- [ ] 历史知识库数据与行为不变

## 相关文档

- `docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md` — 数据模型
- `docs/superpowers/specs/2026-06-16-document-append-chunking-design.md` — append 每文档 rule 行
- `docs/superpowers/specs/2026-06-16-document-segment-config-design.md` — 文档级 process_rule 加载
