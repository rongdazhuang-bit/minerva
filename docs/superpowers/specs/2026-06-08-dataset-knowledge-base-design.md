# 知识库（Dataset）模块设计

**状态：** 已实现（P1–P5 核心能力已落地，E2E 集成测试为可选占位）  
**日期：** 2026-06-08  
**参考：** Dify `dify-main`（`D:\IdeaProjects\gedi-dify\dify-main`）  
**Minerva 约定：** 无库级外键；`workspace_id` 隔离；二次确认使用 Popconfirm；环境变量同步 `backend/.env.example` 与 `backend/.env.dev`

---

## 1. 目标与范围

在 Minerva 内实现接近 Dify 的完整知识库模块：

| 包含 | 不包含（首版） |
|------|----------------|
| 知识库列表 | Notion / Web 数据源 |
| 新建三步向导（仅文件上传） | Pipeline / 外部知识库 |
| 文档列表、详情、分段 CRUD | 多模态文档 |
| 召回测试（Hit Testing） | 自定义元数据字段 |
| 知识库设置（分段/索引/检索，可编辑） | Dify 计费/配额 |
| 完整索引流水线 + Vector 抽象层 | 20+ VDB 全量（Phase 1 仅 pgvector/Qdrant/Weaviate） |

### 1.1 已确认决策

| 项 | 决策 |
|----|------|
| 前端模块 | `frontend/src/features/dataset/` |
| URL | `/app/dataset`（替换 `knowledge-base`） |
| 后端模块 | `backend/app/dataset/`（新建） |
| 表前缀 | `dataset_` |
| UI | Ant Design + Minerva 主题变量，语义对齐 Dify |
| 向量存储 | 移植 Dify `Vector` / `BaseVector` / `VectorFactory`，可配置切换 |
| Step 1 数据源 | 仅文件上传 |
| 详情页 | 文档 + 召回测试 + 设置；文档操作在表格操作列 |

### 1.2 架构方案

**采用方案 A：** 在 `app/dataset` 单模块内嵌移植 Dify `core/rag` 与 `infrastructure/vector`，与 `file_ocr`、`translate` 模块风格一致。

---

## 2. 路由与信息架构

### 2.1 前端路由

| 路径 | 页面 |
|------|------|
| `/app/dataset` | 知识库列表（含筛选区 + 全屏弹窗新建） |
| `/app/dataset/:datasetId/documents` | 文档列表（默认 Tab） |
| `/app/dataset/:datasetId/documents/create` | 向已有库追加文档 |
| `/app/dataset/:datasetId/documents/:documentId` | 文档详情 + 分段 |
| `/app/dataset/:datasetId/hit-testing` | 召回测试 |
| `/app/dataset/:datasetId/settings` | 知识库设置 |

详情 Layout：`DatasetSectionLayout`，左侧 Menu/Tabs（文档 / 召回测试 / 设置）。

### 2.2 后端 API 前缀

```
/workspaces/{workspace_id}/datasets/...
```

鉴权：`require_workspace_member`（与 dict、rule 一致）。

---

## 3. 数据模型（`dataset_` 前缀）

> Dify 表名 → Minerva 表名；**无 FOREIGN KEY**；关联列加索引；删除顺序在 service 层实现。

### 3.1 核心表

#### `dataset`（对应 Dify `datasets`）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | uuid PK | |
| `workspace_id` | uuid NOT NULL, index | 租户隔离（Dify `tenant_id`） |
| `name` | varchar(255) NOT NULL | |
| `description` | text NULL | |
| `provider` | varchar(255) DEFAULT 'vendor' | 首版固定 vendor |
| `permission` | varchar(255) DEFAULT 'only_me' | only_me / all_team_members / partial_members |
| `data_source_type` | varchar(255) | 首版 `upload_file` |
| `indexing_technique` | varchar(255) NULL | `high_quality` / `economy` |
| `index_struct` | text NULL | JSON：向量库 type + collection 信息 |
| `embedding_model` | varchar(255) NULL | 高质量模式 |
| `embedding_model_provider` | varchar(255) NULL | 对应 Minerva provider_name |
| `keyword_number` | int DEFAULT 10 | 经济模式关键词数 |
| `collection_binding_id` | uuid NULL | → `dataset_collection_binding.id` |
| `retrieval_model` | jsonb NULL | 检索配置（见 §4.3） |
| `chunk_structure` | varchar(255) NULL | text_model / qa_model / hierarchical_model |
| `created_by` | uuid NOT NULL | |
| `updated_by` | uuid NULL | |
| `create_at` / `update_at` | timestamptz | |

#### `dataset_process_rule`（对应 `dataset_process_rules`）

| 列 | 说明 |
|----|------|
| `id`, `dataset_id`, `mode`, `rules` (text JSON), `created_by`, `create_at` | |

- `mode`: `automatic` / `custom` / `hierarchical`
- `rules` 结构对齐 Dify `Rule`（pre_processing_rules、segmentation、parent_mode、subchunk_segmentation 等）

#### `dataset_document`（对应 `documents`）

| 列 | 说明 |
|----|------|
| 标识 | `id`, `workspace_id`, `dataset_id`, `position`, `batch`, `name` |
| 来源 | `data_source_type`, `data_source_info` (text JSON), `file_id`, `created_from` |
| 规则 | `dataset_process_rule_id`, `doc_form`, `doc_type`, `doc_language` |
| 索引状态 | `indexing_status`, `processing_started_at`, `parsing_completed_at`, `cleaning_completed_at`, `splitting_completed_at`, `completed_at`, `error`, `stopped_at` |
| 统计 | `word_count`, `tokens`, `indexing_latency` |
| 控制 | `enabled`, `disabled_at`, `disabled_by`, `archived`, `archived_*`, `is_paused`, `paused_*` |
| 审计 | `created_by`, `create_at`, `update_at` |

`indexing_status`: waiting → parsing → cleaning → splitting → indexing → completed | error

#### `dataset_document_segment`（对应 `document_segments`）

| 列 | 说明 |
|----|------|
| `id`, `workspace_id`, `dataset_id`, `document_id`, `position` | |
| `content`, `answer` (Q&A), `word_count`, `tokens` | |
| `keywords` (jsonb), `index_node_id`, `index_node_hash` | |
| `hit_count`, `enabled`, `status`, `error` | |
| 审计列 | |

#### `dataset_child_chunk`（对应 `child_chunks`）

父子分段模式下的子块；列对齐 Dify `ChildChunk`。

#### `dataset_keyword_table`（对应 `dataset_keyword_tables`）

| 列 | 说明 |
|----|------|
| `id`, `dataset_id` UNIQUE, `keyword_table` (text), `data_source_type` | 经济模式倒排 |

#### `dataset_embedding`（对应 `embeddings`）

嵌入缓存：`model_name`, `hash`, `embedding` (bytea), `provider_name`, `create_at`；唯一约束 `(model_name, hash, provider_name)`。

#### `dataset_collection_binding`（对应 `dataset_collection_bindings`）

| 列 | 说明 |
|----|------|
| `provider_name`, `model_name`, `type`, `collection_name`, `create_at` | 同模型共享 collection |

#### `dataset_query`（对应 `dataset_queries`）

召回测试历史：`dataset_id`, `content`, `source`, `created_by`, `create_at`。

### 3.2 上传文件

复用 Minerva 现有上传能力：新建 `dataset_upload_file` 或在首版直接引用 `sys` 文件存储已上传文件 ID（实现阶段二选一，API 层对齐 Dify `upload_file_id` 语义）。

推荐：**独立表 `dataset_upload_file`**，字段对齐 Dify `UploadFile`（`id`, `workspace_id`, `storage_key`, `name`, `size`, `extension`, `mime_type`, `created_by`, `create_at`），便于索引流水线与 Dify `ExtractProcessor.load_from_upload_file` 对接。

### 3.3 应用层删除顺序（示例）

删除知识库（**同步**）：`dataset_child_chunk` → `dataset_document_segment` → `dataset_document` → `dataset_process_rule` → `dataset_keyword_table` → `dataset_query` → `dataset`。

删除知识库（**异步 Celery `dataset.cleanup`**）：`dataset_upload_file` 行 + S3 `storage_key` 对象 + 向量库 collection（high_quality）。外部清理失败不阻断 DELETE API。详见 `2026-06-16-segment-save-then-reprocess-upload-cleanup-design.md`。

删除文档：子块 → 分段 → 向量节点 → 文档行。

---

## 4. 索引与检索

### 4.1 文档解析（移植 Dify）

源码路径：`api/core/rag/extractor/` → `app/dataset/rag/extractor/`

**依赖（对齐 Dify `pyproject.toml` 子集）：**

- `beautifulsoup4`, `python-docx`, `pypdfium2`, `unstructured[docx,epub,md,ppt,pptx]`, `jieba`, `markdown` 等
- 入口：`ExtractProcessor.load_from_upload_file`

**支持扩展名（与 Dify Step 1 一致）：**  
TXT, MARKDOWN, MD, MDX, PDF, DOCX, HTML, HTM, CSV, XLS, XLSX, VTT, PROPERTIES 等。

### 4.2 分段与索引处理器

| doc_form | 处理器 | 说明 |
|----------|--------|------|
| `text_model` | ParagraphIndexProcessor | 通用分段 |
| `hierarchical_model` | ParentChildIndexProcessor | 父子分段 |
| `qa_model` | QAIndexProcessor | Q&A 分段（可选，UI 有则启用） |

流程（`IndexingRunner` 移植）：

1. **extract** — ExtractProcessor  
2. **transform** — CleanProcessor + TextSplitter（delimiter、max length、overlap）  
3. **load segments** — 写入 `dataset_document_segment` / `dataset_child_chunk`  
4. **index** — 高质量：Embedding（`CacheEmbedding` + `dataset_embedding` 缓存）→ Vector.add_texts；经济：Keyword 表 + `dataset_keyword_table`  
5. 更新文档状态与时间戳

异步：**Celery** `dataset_document_indexing_task`（queue=`dataset`），状态轮询 API 对齐 Dify `indexing-status`。

### 4.3 检索配置 JSON（`retrieval_model`）

```json
{
  "search_method": "semantic_search | full_text_search | hybrid_search",
  "reranking_enable": false,
  "reranking_mode": "weighted_score | reranking_model",
  "reranking_model": {
    "reranking_provider_name": "",
    "reranking_model_name": ""
  },
  "weights": { "vector_setting": { "vector_weight": 0.7 }, "keyword_setting": { "keyword_weight": 0.3 } },
  "top_k": 3,
  "score_threshold_enabled": false,
  "score_threshold": 0.5
}
```

### 4.4 Vector 抽象层

移植路径：

- `vector_base.py` → `BaseVector`
- `vector_factory.py` → `Vector`, `AbstractVectorFactory`
- `vector_type.py` → 枚举

**Phase 1 实现：** `pgvector`, `qdrant`, `weaviate`  
**Phase 2+：** factory 按 Dify match 扩展（Milvus、Chroma、ES…）

配置：

- 全局默认：`DATASET_VECTOR_STORE`
- 单库覆盖：`dataset.index_struct.type`（创建时写入）

Collection 命名：`{DATASET_VECTOR_INDEX_NAME_PREFIX}_{dataset_id}_Node`（对齐 Dify `Dataset.gen_collection_name_by_id`）。

嵌入模型：通过 `sys_models`（tag=`EMBEDDINGS`）解析为 OpenAI-compatible endpoint；Rerank 用 tag=`RERANKING`。

### 4.5 召回测试

移植 `HitTestingService.retrieve` + `RetrievalService`：

- POST `.../datasets/{id}/hit-testing`，body: `{ "query": "...", "retrieval_model": {...} }`（可选覆盖）
- 记录 `dataset_query`
- 返回分段内容、score、document 元信息

---

## 5. REST API 清单

### 5.1 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/datasets` | 分页列表；Query：`name`（知识库名称模糊）、`indexing_technique`（可选）、`created_from` / `created_to`（ISO 日期） |
| POST | `/datasets` | 创建空库（可选，列表页「创建空知识库」） |
| GET | `/datasets/{id}` | 详情 |
| PATCH | `/datasets/{id}` | 更新名称/描述/retrieval_model 等 |
| DELETE | `/datasets/{id}` | 删除（Popconfirm） |
| GET | `/datasets/process-rule` | 默认分段规则 |
| POST | `/datasets/indexing-estimate` | 创建前分段预览（Step 2） |
| POST | `/datasets/init` | 首次创建库 + 文档（Step 3 提交） |

### 5.2 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/datasets/{id}/documents` | 分页列表 |
| POST | `/datasets/{id}/documents` | 追加文档 |
| GET | `/datasets/{id}/documents/{doc_id}` | 详情 |
| DELETE | `/datasets/{id}/documents/{doc_id}` | 删除 |
| PATCH | `/datasets/{id}/documents/{doc_id}` | 重命名等 |
| POST | `/datasets/{id}/documents/{doc_id}/status/{enable\|disable}` | 启用/禁用 |
| GET | `/datasets/{id}/documents/{doc_id}/indexing-status` | 单文档进度 |
| GET | `/datasets/{id}/batch/{batch}/indexing-status` | 批次进度（Step 3） |
| POST | `/datasets/{id}/retry` | 失败重试 |
| POST | `/datasets/{id}/documents/{doc_id}/processing/pause` | 暂停 |
| POST | `/datasets/{id}/documents/{doc_id}/processing/resume` | 恢复 |

### 5.3 分段

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/datasets/{id}/documents/{doc_id}/segments` | 分页列表 |
| POST | `/datasets/{id}/documents/{doc_id}/segment` | 新增分段 |
| PATCH | `/datasets/{id}/documents/{doc_id}/segments/{seg_id}` | 编辑 |
| DELETE | `/datasets/{id}/documents/{doc_id}/segments/{seg_id}` | 删除 |
| POST | `/datasets/{id}/documents/{doc_id}/segments/{seg_id}/enable` | 启用/禁用 |

父子模式：child_chunks 子资源对齐 Dify `datasets_segments.py`。

### 5.4 召回测试

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/datasets/{id}/hit-testing` | 执行召回 |
| GET | `/datasets/{id}/queries` | 历史查询 |

### 5.5 文件

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/datasets/files/upload` | 上传（或复用 workspace 文件 API + 登记） |

### 5.6 设置页可编辑规则

| 字段 | 创建后是否可改 |
|------|----------------|
| `indexing_technique` | 高质量嵌入完成后 **不可** 改回 economy（与 Dify 一致） |
| `embedding_model` | 有已索引文档时限制变更（需 re-index 提示） |
| `retrieval_model` | **可改** |
| `dataset_process_rule` | **可改**；变更后对新文档生效；已有文档需「重新索引」操作（Phase 1 可提示，批量 re-index Phase 2） |

---

## 6. 前端设计

### 6.1 模块结构

```
frontend/src/features/dataset/
├── index.ts
├── api/                    # datasets.ts, documents.ts, segments.ts, hitTesting.ts
├── DatasetListPage.tsx       # 筛选 Form + 列表 + 新建 Modal 入口
├── create/
│   ├── DatasetCreateWizard.tsx   # 三步向导（Modal 内嵌）
│   ├── StepOneUpload.tsx
│   ├── StepTwoChunking.tsx
│   ├── StepThreeProcessing.tsx
│   └── WizardStepper.tsx
├── layout/
│   └── DatasetSectionLayout.tsx
├── documents/
│   ├── DocumentListPage.tsx
│   ├── DocumentDetailPage.tsx
│   └── DocumentCreateWizard.tsx  # 复用 Step 组件
├── hit-testing/
│   └── HitTestingPage.tsx
├── settings/
│   └── DatasetSettingsPage.tsx
└── components/
    ├── ChunkingSettingsForm.tsx
    ├── IndexingModeForm.tsx
    ├── RetrievalSettingsForm.tsx
    ├── SegmentPreviewPanel.tsx
    └── ...
```

### 6.2 知识库列表页（筛选 + 新建入口）

布局参考 `FileOcrTaskPage` 顶部 inline `Form`（Ant Design），字段与截图一致：

| 表单项 | 组件 | 说明 |
|--------|------|------|
| **知识库** | `Input` + `allowClear` | 名称关键词，对应 API `name` |
| **状态** | `Select` + `allowClear` | 可选：索引方式 `high_quality` / `economy`，或「有/无文档」；首版至少支持 `indexing_technique` |
| **创建时间** | `DatePicker.RangePicker` | 占位「创建开始 → 创建结束」，映射 `created_from` / `created_to` |
| **搜索** | `Button type="primary"` | 提交表单，重置 `page=1` |
| **重置** | `Button` | 清空表单并刷新列表 |
| **新建知识库** | `Button type="primary"`（或 `default`，位于重置右侧） | 打开全屏创建弹窗，**不跳转独立路由** |

列表主体：`Table` 或 `Card` 网格展示查询结果；行点击 → `/app/dataset/:id/documents`。

### 6.3 新建向导（全屏 Modal）

**容器：** Ant Design `Modal`，`width="100%"`，`style={{ top: 0, maxWidth: '100vw', padding: 0 }}`，`styles.body` 高度 `calc(100dvh - 110px)`、`overflow: auto`；`footer={null}` 或自定义底部「上一步/下一步」；`destroyOnHidden`；索引进行中禁止 mask/ Esc 关闭（对齐 OCR 向导）。

**打开方式：** 仅由列表页「新建知识库」触发；`DatasetCreateWizard` 为独立组件，供 Modal 与「向已有库追加文档」复用。

**完成行为：** Step 3 成功后关闭 Modal → 刷新列表 → `navigate('/app/dataset/:newId/documents')`（可选）。

**Step 1 — 选择数据源**

- 仅展示「导入已有文本」卡片（可用 Radio.Card / 单选卡片）
- `Upload.Dragger`：支持格式与限制文案对齐 Dify（每批 ≤10，单文件 ≤100MB，总数 ≤5）
- 底部「下一步」：至少 1 个文件成功上传后启用

**Step 2 — 文本分段与清洗**

- 左：表单（通用 / 父子分段、索引方式、Embedding 选择、检索设置）
- 右：预览区（选文件 +「预览块」按钮调用 `indexing-estimate`）
- 经济模式：隐藏 Embedding 模型选择
- 混合检索：权重滑块 + Rerank 模型切换

**Step 3 — 处理并完成**

- 进度列表（batch indexing-status 轮询）
- 完成后跳转 `.../documents`

### 6.4 文档列表

- 顶部筛选（库内上下文，**不含**「知识库」条件）：**文件名**、**状态**、**创建时间范围**、搜索、重置（布局同 §6.2）
- Ant Design `Table`：名称、分段数、字数、索引状态（Tag）、启用状态、上传时间
- **操作列**：启用/禁用、删除（Popconfirm）、查看分段、重试（error 时）、暂停/恢复（indexing 时）
- 「追加文档」：同 §6.3 全屏 Modal，传入已有 `datasetId`

### 6.5 设置 / 召回测试

- 设置：复用 Step 2 表单组件，`PATCH /datasets/{id}` + 更新 process_rule
- 召回测试：Input + 检索参数覆盖（可选）+ 结果 Cards 展示 content/score/source

### 6.6 i18n

新增 `dataset.*` 键于 `zh-CN.json` / `en.json`，含 `dataset.list.filter.knowledgeBase`、`dataset.list.create`、`dataset.create.modalTitle`；导航 `nav.dataset` 替换 `nav.knowledgeBase`。

---

## 7. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DATASET_VECTOR_STORE` | `pgvector` | 向量后端类型 |
| `DATASET_VECTOR_INDEX_NAME_PREFIX` | `Vector_index` | Collection 前缀 |
| `DATASET_KEYWORD_STORE` | `jieba` | 经济模式 |
| `DATASET_BATCH_UPLOAD_LIMIT` | `10` | |
| `DATASET_MAX_FILES_PER_DATASET` | `5` | 创建时总文件数 |
| `DATASET_SINGLE_FILE_SIZE_LIMIT_MB` | `100` | |
| `DATASET_PGVECTOR_URL` | | pgvector 连接（可与主库或独立库） |
| `DATASET_QDRANT_URL` | | |
| `DATASET_QDRANT_API_KEY` | | |
| `DATASET_WEAVIATE_ENDPOINT` | | |
| `DATASET_WEAVIATE_API_KEY` | | |

---

## 8. 测试策略

| 层级 | 内容 |
|------|------|
| 单元 | ExtractProcessor 各格式样例、TextSplitter、Rule JSON 解析 |
| 集成 | API：init → indexing-status → documents list；hit-testing |
| 向量 | pgvector 本地 docker；Qdrant/Weaviate 可选 CI skip |
| 前端 | 向导 happy path；文档操作列 Popconfirm |

---

## 9. 分期交付建议

| 阶段 | 交付物 |
|------|--------|
| **P1** | 表结构 + ORM + 文件上传 + ExtractProcessor 移植 + 列表/创建空壳 |
| **P2** | IndexingRunner + Celery + pgvector + 三步向导 E2E |
| **P3** | 文档列表/详情/分段 CRUD + 设置页 |
| **P4** | 召回测试 + Qdrant/Weaviate + Rerank/混合检索 |
| **P5** | 父子分段、Q&A 分段、失败重试/暂停恢复 polish |

---

## 10. 实现对照（以代码为准）

| Spec 条目 | 计划代码位置 | 状态 |
|-----------|--------------|------|
| ORM + 迁移 | `backend/app/dataset/domain/db/models.py`、`alembic/versions/g7h8i9j0k1l2_dataset_tables.py` | 已完成 |
| Vector | `backend/app/dataset/infrastructure/vector/`（pgvector / Qdrant / Weaviate） | 已完成 |
| RAG + 分段模式 | `backend/app/dataset/rag/`（text / hierarchical / Q&A） | 已完成 |
| API | `backend/app/dataset/api/router.py`（列表、向导、文档、分段、召回、设置） | 已完成 |
| Celery | `backend/app/dataset/task/`（queue=`dataset`） | 已完成 |
| 前端 | `frontend/src/features/dataset/`（向导、文档、召回、设置） | 已完成 |
| E2E 集成 | `backend/tests/test_dataset_integration.py` | 占位（`RUN_DATASET_INTEGRATION=1`） |
| 手动分段 CRUD | `segment_service` + `index_sync_service` | 已完成（含父子 child_chunk 同步） |
| 子块 CRUD API | `POST/PATCH/DELETE .../child_chunks` | 已完成（对齐 Dify） |
| 空库创建 | `POST /datasets` | 已完成 |
| 单文档索引状态 | `GET .../documents/{id}/indexing-status` | 已完成 |
| Celery 队列 | `scripts/run-celery.*` | 默认 `-Q default,dataset` |

### 部署备忘

- Alembic head：`g7h8i9j0k1l2`（依赖 `f6a7b8c9d0e1`）。老库若版本链断裂，可 `stamp` 到上一 revision 后 `upgrade head`。
- Celery Worker 须订阅 **`dataset`** 队列。
- 高质量索引需 pgvector 扩展 + 已启用的 Embeddings 模型；可选 `pip install -e ".[vector]"` 启用 Qdrant/Weaviate。

---

## 附录 A：Dify 源码索引

| 能力 | Dify 路径 |
|------|-----------|
| ORM | `api/models/dataset.py` |
| 创建 UI | `web/app/components/datasets/create/` |
| 列表 | `web/app/(commonLayout)/datasets/` |
| 索引 | `api/core/indexing_runner.py` |
| 向量 | `api/core/rag/datasource/vdb/` |
| 解析 | `api/core/rag/extractor/extract_processor.py` |
| API | `api/controllers/console/datasets/datasets*.py` |
| 召回 | `api/services/hit_testing_service.py` |
