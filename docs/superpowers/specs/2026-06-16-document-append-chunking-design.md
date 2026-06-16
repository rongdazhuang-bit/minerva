# 添加文档 — 分段配置与完成页设计

**日期：** 2026-06-16  
**状态：** 待审阅  
**范围：** 知识库 → 文档列表 →「添加文档」全屏向导（`DatasetCreateWizard` append 模式）

## 背景

当前「添加文档」为 2 步流程：上传文件后点击「开始索引」即调用 `appendDocuments` 并跳过配置，进入简版处理页（`StepThreeProcessing` + `isAppend=true`），缺少分段配置步骤，完成页也无配置摘要与「接下来做什么」侧栏。

目标：与创建知识库向导对齐为 3 步；中间增加整批分段配置与预览；完成页展示与创建向导 Step 3 一致的完整 UI（标题改为「文档已上传」）。

## 需求摘要

| # | 需求 | 说明 |
|---|------|------|
| 1 | 按钮文案 | Step 0 主按钮由「开始索引」改为「下一步」 |
| 2 | 新增 Step 1 | 整批共用分段配置 + 右侧文件预览 |
| 3 | 保存并处理 | Step 1 提交 `process_rule` 并创建文档、入队索引 |
| 4 | 完整完成页 | Step 2 使用创建向导同款布局（配置摘要、侧栏、前往文档） |
| 5 | 文档级 rule 行 | UI 一套配置；DB 每个新文档各绑定独立 `DatasetProcessRule` 行（内容相同） |

## 方案选择

采用 **方案 A**：扩展 `POST /datasets/{id}/documents`（append）接受 `process_rule`，后端为每个文档新建独立 rule 行后入队索引。

未采用先 append 再循环 PATCH（方案 B，N 次请求、重复处理）或草稿/确认双 API（方案 C，过度设计）。

## 交互设计

### 步骤条（append 模式）

与创建知识库一致，显示 3 步：

1. **选择数据源** — 上传文件  
2. **文本分段与清洗** — 配置与预览  
3. **处理并完成** — 嵌入进度与摘要  

### Step 0 — 上传

- 复用 `StepOneUpload`（不传 `form`，无知识库名称字段）
- 主按钮：**下一步**（`dataset.create.next`），`uploads.length === 0` 时 disabled
- 点击后 `setStep(1)`，**不**调用 API

### Step 1 — 分段配置与预览

布局：`ChunkingConfigPreviewLayout` 左右分栏。

| 区域 | 组件 | 可编辑 |
|------|------|--------|
| 左 | `SegmentationSettingsPanel` | ✅ |
| 左 | `IndexingMethodPanel`（`indexingLocked` + `embeddingReadOnly`） | ❌ |
| 左 | `RetrievalSettingsPanel`（`retrievalLocked`） | ❌ |
| 右 | `ChunkPreviewPanel`（下拉切换本次上传的 `file_id`） | 预览 |

**预填与锁定：**

- `GET /datasets/{id}` → 索引、Embedding、检索、 `chunk_structure`（`doc_form` 锁定，不可改）
- `get_latest_process_rule` 或等价数据 → 分段字段默认值
- 禁止回退到 workspace 全局默认（应基于目标知识库）

**底部：**「上一步」+「保存并处理」（`dataset.create.saveAndProcess`）

### Step 2 — 处理并完成

与创建向导 Step 3 同款布局，通过 `completionVariant: 'append'` 区分文案：

| 元素 | 创建 | 添加文档 |
|------|------|----------|
| 主标题 | 知识库已创建 | **文档已上传** |
| 副标题 | 自动命名提示 | 可在文档列表中找到（含文件名摘要） |
| 名称输入 | 有 | **无** |
| 配置摘要 | 有 | 有（来自 Step 1 `formSnapshot`） |
| 操作按钮 | API + 前往文档 | 同左 |
| 右侧栏 | 接下来做什么 | 同左 |

废弃 append 简版 UI（`isAppend` 精简分支）；轮询逻辑复用 `getBatchIndexingStatus`。

## 前端实现

### 主要文件

| 文件 | 变更 |
|------|------|
| `frontend/src/features/dataset/create/DatasetCreateWizard.tsx` | append 改为 3 步；Step 0 下一步；Step 1 配置；Step 2 带 `formSnapshot` 的完成页 |
| `frontend/src/features/dataset/create/StepTwoChunking.tsx` 或新建 `AppendChunkingStep.tsx` | append 模式：无名称字段、索引/检索只读、`doc_form` 锁定 |
| `frontend/src/features/dataset/create/StepThreeProcessing.tsx` | `completionVariant` 替代 `isAppend` 精简布局 |
| `frontend/src/features/dataset/api/documents.ts` | `appendDocuments` body 增加 `process_rule?` |
| `frontend/src/i18n/locales/zh-CN.json`、`en.json` | append 完成页标题/副标题 |

### Append Step 1 数据流

```text
uploads (StepOneUpload)
  → GET dataset → indexing/retrieval/doc_form 只读
  → GET latest process_rule → 分段表单预填
  → ChunkPreviewPanel 按 upload file_id 切换预览

保存并处理:
  form.validateFields() → buildProcessRule(values, defaultRule)
  → appendDocuments(workspaceId, datasetId, { file_ids, process_rule })
  → setInitResult + setCreateSnapshot(values) + setStep(2)
```

### Wizard 状态（append）

- `handleAppend` 从 Step 0 移至 Step 1「保存并处理」
- `createSnapshot` 在 append 流程同样写入，供 Step 2 配置摘要使用
- `onIndexingChange(true)` 在提交 append 时设置，完成轮询后 `false`

## 后端实现

### API 变更

```python
class DatasetDocumentAppendIn(BaseModel):
    file_ids: list[uuid.UUID] = Field(min_length=1)
    process_rule: dict[str, Any] | None = None
```

### `append_documents` 逻辑

当 `process_rule` 提供时，对每个 `file_id`：

1. 校验 upload 存在且属当前 workspace  
2. **新建** `DatasetProcessRule`（`dataset_id`、`rules=serialize(process_rule)`）  
3. 创建 `DatasetDocument`，`dataset_process_rule_id = 新 rule.id`  
4. `indexing_status = waiting`，同一 `batch`  

全部 flush/commit 后 `_enqueue_indexing(dataset_id, document_ids)`。

当 `process_rule` 未提供时：**保持现有行为**（共用 `get_latest_process_rule` 的 id），兼容旧客户端。

### 与 `init_dataset` 的差异

`init_dataset` 多文档仍共用一条 `DatasetProcessRule`（本次不改）。仅 append 路径保证每文档独立 rule 行，便于后续单文档「分段」弹窗独立修改。

## 端到端数据流

```text
文档列表 → 添加文档
  → Step 0: 上传 → 下一步
  → Step 1: 配置预览 → 保存并处理
      POST /documents { file_ids, process_rule }
      → N 条 DatasetProcessRule + N 条 DatasetDocument
      → enqueue
  → Step 2: 轮询 batch → 配置摘要 → 前往文档 / 关闭
```

## 边界情况

| 场景 | 处理 |
|------|------|
| 未选文件 | 下一步 disabled |
| 知识库无 process_rule 且请求未带 rule | 422；前端提示 |
| `doc_form` | 锁定为 dataset `chunk_structure` |
| 索引进行中 | Modal 禁止关闭（现有 `indexingInProgress`） |
| 多文件上传 | UI 一套配置；DB N 条独立 rule（内容相同） |
| 仅 API 传 `file_ids`（无 rule） | 行为与现网一致 |

## 测试

### 后端

- append 带 `process_rule`：N 文档 → N 条 `dataset_process_rule`，`rules` 内容一致、id 不同  
- 保存后 `indexing_status == waiting` 且任务入队  
- 不带 `process_rule`：仍绑定 latest rule，行为不变  

### 前端

- append 三步步骤条与导航  
- Step 0 按钮为「下一步」  
- Step 1 分段可编辑、索引/检索只读  
- Step 2 完整完成页（标题、摘要、侧栏、前往文档）  

## 不在范围

- 修改 `init_dataset` 的 rule 共享策略  
- 添加文档时每个文件不同分段配置（UI 不支持）  
- 操作列「分段」弹窗（见 `2026-06-16-document-segment-config-design.md`）  
- 完成页单文件百分比进度条（若现有 API 无进度字段，沿用状态图标；后续可单独增强）  

## 参考

- 创建向导：`DatasetCreateWizard`、`StepTwoChunking`、`StepThreeProcessing`  
- 文档分段弹窗：`DocumentSegmentConfigPanel`（只读索引/检索模式）  
- 现有 append：`document_service.append_documents`  
- 相关 spec：`2026-06-16-document-segment-config-design.md`
