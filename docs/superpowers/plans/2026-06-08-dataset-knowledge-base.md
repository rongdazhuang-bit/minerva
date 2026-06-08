# 知识库（Dataset）模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Minerva 实现接近 Dify 的完整知识库模块：列表、三步创建向导（仅文件上传）、文档/分段管理、召回测试、知识库设置；后端 `app/dataset` 移植 RAG + Vector 抽象层；表前缀 `dataset_`；路由 `/app/dataset`。

**Architecture:** 单模块 `backend/app/dataset/` 内嵌 Dify `core/rag` 与 `infrastructure/vector`；API 前缀 `/workspaces/{workspace_id}/datasets`；`workspace_id` 隔离、无库级外键；Celery queue `dataset` 异步索引；嵌入/Rerank 走 `sys_models`（`EMBEDDINGS`/`RERANKING`）；Phase 1 向量库 pgvector，Phase 2 补 Qdrant/Weaviate。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, Celery, pytest+httpx；React 18, Ant Design 6, react-i18next；移植依赖：unstructured, python-docx, pypdfium2, jieba, beautifulsoup4。

**设计依据:** `docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md`

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/alembic/versions/<rev>_dataset_tables.py` | 全部 `dataset_*` 表（无 FK） |
| `backend/sql/schema_postgresql.sql` | 同步 DDL |
| `backend/app/dataset/domain/db/models.py` | ORM |
| `backend/app/dataset/domain/constants.py` | 状态枚举、检索方法常量 |
| `backend/app/dataset/rag/**` | 自 Dify 移植：extractor, cleaner, splitter, index_processor, indexing_runner |
| `backend/app/dataset/infrastructure/vector/**` | BaseVector, VectorFactory, pgvector/qdrant/weaviate |
| `backend/app/dataset/infrastructure/repository.py` | 查询/分页 |
| `backend/app/dataset/service/*.py` | dataset, document, segment, hit_testing, indexing |
| `backend/app/dataset/task/indexing_task.py` | Celery 任务 |
| `backend/app/dataset/api/router.py`, `schemas.py` | REST |
| `backend/app/config.py` | DATASET_* 环境变量 |
| `backend/.env.example`, `backend/.env.dev` | 同步 env |
| `backend/app/core/api/router.py` | include dataset router |
| `backend/app/core/infrastructure/db/bootstrap.py` | import dataset models |
| `backend/app/celery_app.py` | 注册 dataset 任务模块 |
| `backend/pyproject.toml` | RAG 依赖 |
| `backend/tests/test_dataset_*.py` | API + 单元测试 |
| `frontend/src/features/dataset/**` | 全部 UI |
| `frontend/src/app/router.tsx` | 路由 `dataset` |
| `frontend/src/app/layout/AppLayout.tsx`, `AppBreadcrumb.tsx` | 导航 |
| `frontend/src/features/workspace/OverviewPage.tsx` | 入口卡片 |
| `frontend/src/i18n/locales/zh-CN.json`, `en.json` | `dataset.*` |

> **Alembic head（编写时）:** `f6a7b8c9d0e1` — 新迁移 `down_revision` 指向该 revision。

---

## Phase P1 — 基础骨架

### Task 1: 环境变量与配置

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`

- [ ] **Step 1:** 在 `Settings` 中新增字段（含 `validation_alias`）：

```python
dataset_vector_store: str = Field(default="pgvector", validation_alias=AliasChoices("DATASET_VECTOR_STORE", ...))
dataset_vector_index_name_prefix: str = Field(default="Vector_index", ...)
dataset_keyword_store: str = Field(default="jieba", ...)
dataset_batch_upload_limit: int = Field(default=10, ge=1, ...)
dataset_max_files_per_dataset: int = Field(default=5, ge=1, ...)
dataset_single_file_size_limit_mb: int = Field(default=100, ge=1, ...)
dataset_pgvector_url: str = Field(default="", ...)
dataset_qdrant_url: str = Field(default="", ...)
dataset_qdrant_api_key: str = Field(default="", ...)
dataset_weaviate_endpoint: str = Field(default="", ...)
dataset_weaviate_api_key: str = Field(default="", ...)
```

- [ ] **Step 2:** 在 `.env.example` 与 `.env.dev` 追加同名变量及注释。
- [ ] **Step 3:** 运行 `cd backend; python -c "from app.config import settings; print(settings.dataset_vector_store)"`，期望输出 `pgvector`。

---

### Task 2: Alembic 迁移 — `dataset_*` 表

**Files:**
- Create: `backend/alembic/versions/g7h8i9j0k1l2_dataset_tables.py`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1:** 创建 migration，`down_revision = "f6a7b8c9d0e1"`，在 `upgrade()` 中依次 `op.create_table`（**无 FOREIGN KEY**）：

  1. `dataset` — 列见 spec §3.1；索引 `ix_dataset_workspace_id`
  2. `dataset_process_rule` — 索引 `ix_dataset_process_rule_dataset_id`
  3. `dataset_upload_file` — `id`, `workspace_id`, `storage_key`, `name`, `size`, `extension`, `mime_type`, `created_by`, `create_at`
  4. `dataset_document` — 索引 `ix_dataset_document_dataset_id`, `ix_dataset_document_workspace_id`
  5. `dataset_document_segment` — 复合索引 `(document_id, dataset_id)`, `(index_node_id, dataset_id)`
  6. `dataset_child_chunk` — 索引 `(segment_id)`, `(tenant_id, dataset_id, document_id, segment_id)` → 用 `workspace_id`
  7. `dataset_keyword_table` — `dataset_id` UNIQUE
  8. `dataset_embedding` — UNIQUE `(model_name, hash, provider_name)`
  9. `dataset_collection_binding` — 索引 `(provider_name, model_name)`
  10. `dataset_query` — 索引 `ix_dataset_query_dataset_id`

- [ ] **Step 2:** `downgrade()` 按子表→主表顺序 `drop_table`。
- [ ] **Step 3:** 将等价 DDL 追加到 `schema_postgresql.sql`（文件头保留「禁止外键」说明）。
- [ ] **Step 4:** 运行 `cd backend; alembic upgrade head`，期望 SUCCESS。

---

### Task 3: ORM 模型

**Files:**
- Create: `backend/app/dataset/__init__.py`
- Create: `backend/app/dataset/domain/__init__.py`, `domain/db/__init__.py`
- Create: `backend/app/dataset/domain/db/models.py`
- Create: `backend/app/dataset/domain/constants.py`

- [ ] **Step 1:** 在 `constants.py` 定义：

```python
INDEXING_TECHNIQUE_HIGH_QUALITY = "high_quality"
INDEXING_TECHNIQUE_ECONOMY = "economy"
INDEXING_STATUS_WAITING = "waiting"
# ... parsing, cleaning, splitting, indexing, completed, error
RETRIEVAL_SEMANTIC = "semantic_search"
RETRIEVAL_FULL_TEXT = "full_text_search"
RETRIEVAL_HYBRID = "hybrid_search"
DOC_FORM_TEXT = "text_model"
DOC_FORM_HIERARCHICAL = "hierarchical_model"
DOC_FORM_QA = "qa_model"
PROCESS_MODE_CUSTOM = "custom"
PROCESS_MODE_HIERARCHICAL = "hierarchical"
```

- [ ] **Step 2:** 在 `models.py` 定义 ORM 类 `Dataset`, `DatasetProcessRule`, `DatasetUploadFile`, `DatasetDocument`, `DatasetDocumentSegment`, `DatasetChildChunk`, `DatasetKeywordTable`, `DatasetEmbedding`, `DatasetCollectionBinding`, `DatasetQuery` — 列名/类型与 migration 一致；`retrieval_model`/`keywords` 用 `JSONB`；关联列仅 `index=True`，**不用 `ForeignKey`**。

- [ ] **Step 3:** 在 `Dataset` 上添加 `@staticmethod def gen_collection_name(dataset_id: uuid.UUID) -> str`，逻辑对齐 Dify `Dataset.gen_collection_name_by_id`（使用 `settings.dataset_vector_index_name_prefix`）。

---

### Task 4: 注册 ORM 与空路由

**Files:**
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Create: `backend/app/dataset/api/__init__.py`, `api/router.py`, `api/schemas.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1:** `_import_models()` 追加 `import app.dataset.domain.db.models  # noqa: F401`。
- [ ] **Step 2:** 创建 `router = APIRouter(prefix="/workspaces/{workspace_id}/datasets", tags=["datasets"])`，暂挂 `GET /` 返回 `[]` 的占位 handler（带 `require_workspace_member`）。
- [ ] **Step 3:** 在 `core/api/router.py` 中 `from app.dataset.api.router import router as datasets_router` 并 `include_router`。
- [ ] **Step 4:** 启动 API，`GET /api/workspaces/{wid}/datasets` 返回 200（需有效 token）。

---

### Task 5: 文件上传 API

**Files:**
- Create: `backend/app/dataset/service/upload_service.py`
- Modify: `backend/app/dataset/api/router.py`, `schemas.py`
- Create: `backend/tests/test_dataset_upload.py`

- [ ] **Step 1:** 写失败测试：

```python
@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, auth_headers, workspace_id, monkeypatch):
    # POST multipart with file > DATASET_SINGLE_FILE_SIZE_LIMIT_MB
    resp = await client.post(
        f"/api/workspaces/{workspace_id}/datasets/files/upload",
        headers=auth_headers,
        files={"file": ("big.bin", b"x" * (101 * 1024 * 1024), "application/octet-stream")},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2:** 运行 `pytest backend/tests/test_dataset_upload.py -v`，期望 FAIL。
- [ ] **Step 3:** 实现 `upload_service.upload_dataset_file(session, workspace_id, user_id, file)` — 校验扩展名（白名单对齐 Dify）、大小、写入 S3/本地（复用 `app/s3` 或 `sys/file_storage` 已有 client）；插入 `dataset_upload_file` 行；返回 `{id, name, size, extension, mime_type}`。
- [ ] **Step 4:** `POST /datasets/files/upload` handler。
- [ ] **Step 5:** 测试 PASS。

---

## Phase P2 — RAG 移植与索引

### Task 6: 移植 ExtractProcessor（文件解析）

**Files:**
- Create: `backend/app/dataset/rag/extractor/**`（从 Dify 复制并改 import 前缀）
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/test_dataset_extractor.py`

- [ ] **Step 1:** 在 `pyproject.toml` 添加依赖：`beautifulsoup4`, `python-docx`, `pypdfium2`, `unstructured[docx,md,pdf]`, `jieba`, `markdown`（版本对齐 Dify `pyproject.toml`）。
- [ ] **Step 2:** 运行 `cd backend; pip install -e .` 或项目惯用安装命令。
- [ ] **Step 3:** 移植 `extract_processor.py`, `text_extractor.py`, `pdf_extractor.py`, `word_extractor.py`, `markdown_extractor.py`, `html_extractor.py`, `csv_extractor.py`, `excel_extractor.py` 及 `entity/` 子包；将 `UploadFile` 模型引用改为 `DatasetUploadFile`；storage 调用改为 Minerva S3 读取。
- [ ] **Step 4:** 测试用例：

```python
def test_text_extractor_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello 世界", encoding="utf-8")
    docs = TextExtractor(str(p)).extract()
    assert "hello" in docs[0].page_content
```

- [ ] **Step 5:** `pytest backend/tests/test_dataset_extractor.py -v` PASS。

---

### Task 7: 移植 Cleaner + Splitter + IndexProcessor

**Files:**
- Create: `backend/app/dataset/rag/cleaner/clean_processor.py`
- Create: `backend/app/dataset/rag/splitter/**`
- Create: `backend/app/dataset/rag/index_processor/**`
- Create: `backend/tests/test_dataset_chunking.py`

- [ ] **Step 1:** 移植 `CleanProcessor`（remove_extra_spaces, remove_urls_emails）。
- [ ] **Step 2:** 移植 `FixedRecursiveCharacterTextSplitter`, `EnhanceRecursiveCharacterTextSplitter`。
- [ ] **Step 3:** 移植 `ParagraphIndexProcessor`, `ParentChildIndexProcessor`（Q&A 处理器可 Phase P5 再启用）。
- [ ] **Step 4:** 测试：给定 `"a\n\nb\n\nc"` + delimiter `\n\n` + max_length 1024 → 分段数 ≥ 1。

---

### Task 8: Vector 抽象层 — Base + Factory + pgvector

**Files:**
- Create: `backend/app/dataset/infrastructure/vector/vector_base.py`
- Create: `backend/app/dataset/infrastructure/vector/vector_type.py`
- Create: `backend/app/dataset/infrastructure/vector/vector_factory.py`
- Create: `backend/app/dataset/infrastructure/vector/pgvector/pgvector.py`
- Create: `backend/tests/test_dataset_pgvector.py`

- [ ] **Step 1:** 从 Dify 复制 `BaseVector` 抽象方法：`create`, `add_texts`, `delete_by_ids`, `search_by_vector`, `search_by_full_text`, `delete`。
- [ ] **Step 2:** 复制 `VectorType` 枚举，首版保留 `PGVECTOR`, `QDRANT`, `WEAVIATE`。
- [ ] **Step 3:** 实现 `Vector` 类：读 `settings.dataset_vector_store` 或 `dataset.index_struct`；`get_vector_factory()` match 分支。
- [ ] **Step 4:** 移植 `PGVectorFactory` + `PGVector`，连接串用 `settings.dataset_pgvector_url`（空则 fallback 主库 DSN + pgvector extension）。
- [ ] **Step 5:** 集成测试（需 Docker pgvector）：create collection → add_texts → search_by_vector 返回非空。

---

### Task 9: Embedding 缓存与模型解析

**Files:**
- Create: `backend/app/dataset/rag/embedding/cached_embedding.py`
- Create: `backend/app/dataset/service/embedding_resolver.py`
- Create: `backend/tests/test_dataset_embedding_cache.py`

- [ ] **Step 1:** 移植 `CacheEmbedding`：查 `dataset_embedding` by `(model_name, hash, provider_name)`；未命中调 `app.llm.strategies.embedding.EmbeddingStrategy` via `ResolvedModel`。
- [ ] **Step 2:** `embedding_resolver.resolve_embedding_model(session, workspace_id, provider_name, model_name)` — 从 `sys_models` 查 tag 含 `EMBEDDINGS` 的行。
- [ ] **Step 3:** 单元测试：mock embed 返回固定向量，第二次调用不触发 HTTP。

---

### Task 10: IndexingRunner + Celery 任务

**Files:**
- Create: `backend/app/dataset/rag/indexing_runner.py`
- Create: `backend/app/dataset/task/indexing_task.py`
- Modify: `backend/app/celery_app.py`
- Create: `backend/tests/test_dataset_indexing_runner.py`

- [ ] **Step 1:** 移植 `IndexingRunner.run(documents)` 为 async 友好版本（Celery sync wrapper 内用 `asyncio.run` 或 sync session）；流程：extract → transform → load segments → index（high_quality/economy 分支）。
- [ ] **Step 2:** 经济模式移植 `Keyword` factory + `dataset_keyword_table` 写入（jieba）。
- [ ] **Step 3:** Celery 任务：

```python
@shared_task(name="dataset.document_indexing", queue="dataset")
def dataset_document_indexing_task(dataset_id: str, document_ids: list[str]) -> None:
    ...
```

- [ ] **Step 4:** 在 `celery_app.py` autodiscover 或显式 import `app.dataset.task.indexing_task`。
- [ ] **Step 5:** 测试：插入 waiting 文档 → 调用 runner → status 变 completed，segment 表有行。

---

### Task 11: Dataset 初始化 API（创建向导后端）

**Files:**
- Create: `backend/app/dataset/service/dataset_service.py`
- Create: `backend/app/dataset/service/document_service.py`
- Modify: `backend/app/dataset/api/router.py`, `schemas.py`
- Create: `backend/tests/test_dataset_init_api.py`

- [ ] **Step 1:** 实现 `GET /datasets/process-rule` — 返回 Dify 默认 `AUTOMATIC_RULES` JSON。
- [ ] **Step 2:** 实现 `POST /datasets/indexing-estimate` — body 含 `file_ids`, `process_rule`, `indexing_technique`, `doc_form`；调用 runner 的 estimate 路径，返回 preview chunks（不持久化）。
- [ ] **Step 3:** 实现 `POST /datasets/init` — 创建 `dataset` + `dataset_process_rule` + `dataset_document`(batch) + enqueue Celery；返回 `{dataset, documents, batch}`。
- [ ] **Step 4:** 实现 `GET /datasets/{id}/batch/{batch}/indexing-status` — 轮询 Step 3 进度。
- [ ] **Step 5:** API 测试：upload txt → init → poll until completed。

---

## Phase P3 — 文档与分段 CRUD

### Task 12: Dataset 列表/详情/删除

**Files:**
- Modify: `backend/app/dataset/service/dataset_service.py`, `api/router.py`
- Create: `backend/tests/test_dataset_crud_api.py`

- [ ] **Step 1:** `GET /datasets` 分页（默认 page_size=10，用 `app.pagination.DEFAULT_PAGE_SIZE`）；Query 参数：`name: str | None`、`indexing_technique: str | None`、`created_from` / `created_to: datetime | None`（闭区间，按 `create_at` 过滤）。
- [ ] **Step 2:** `GET/PATCH/DELETE /datasets/{id}`；DELETE 按 spec §3.3 顺序清理子表 + vector collection。
- [ ] **Step 3:** API 测试 CRUD + 删除后 segment 为空。

---

### Task 13: 文档列表与操作

**Files:**
- Modify: `backend/app/dataset/service/document_service.py`, `api/router.py`
- Create: `backend/tests/test_dataset_document_api.py`

- [ ] **Step 1:** `GET /datasets/{id}/documents` — 分页，返回 `display_status` 计算字段（对齐 Dify）。
- [ ] **Step 2:** `POST /datasets/{id}/documents` — 向已有库追加（复用 init 逻辑，不新建 dataset）。
- [ ] **Step 3:** `DELETE /datasets/{id}/documents/{doc_id}`；`POST .../status/enable|disable`；`POST .../retry`；`POST .../processing/pause|resume`。
- [ ] **Step 4:** 测试 enable/disable 切换 `enabled` 列。

---

### Task 14: 分段 CRUD

**Files:**
- Create: `backend/app/dataset/service/segment_service.py`
- Modify: `api/router.py`
- Create: `backend/tests/test_dataset_segment_api.py`

- [ ] **Step 1:** `GET /datasets/{id}/documents/{doc_id}/segments` 分页。
- [ ] **Step 2:** `POST .../segment` 新增；`PATCH .../segments/{seg_id}` 编辑 content；`DELETE .../segments/{seg_id}` — 同步更新 vector/keyword 索引。
- [ ] **Step 3:** 父子模式：`GET/POST .../segments/{seg_id}/child_chunks`。
- [ ] **Step 4:** 测试新增分段后 `search_by_vector` 可命中新内容。

---

### Task 15: 知识库设置 API

**Files:**
- Modify: `backend/app/dataset/service/dataset_service.py`, `api/router.py`
- Create: `backend/tests/test_dataset_settings_api.py`

- [ ] **Step 1:** `PATCH /datasets/{id}` 接受 `retrieval_model`, `process_rule`（新建 process_rule 行并关联），校验 high_quality→economy 禁止回退。
- [ ] **Step 2:** 测试：completed 文档 + high_quality 库 PATCH `indexing_technique=economy` 返回 422。

---

## Phase P4 — 召回测试与扩展向量库

### Task 16: 召回测试 API

**Files:**
- Create: `backend/app/dataset/rag/retrieval/retrieval_service.py`
- Create: `backend/app/dataset/service/hit_testing_service.py`
- Modify: `api/router.py`
- Create: `backend/tests/test_dataset_hit_testing_api.py`

- [ ] **Step 1:** 移植 `RetrievalService.retrieve` — semantic / full_text / hybrid 三分支；hybrid 支持 weighted_score 与 reranking_model。
- [ ] **Step 2:** Rerank 调 `app.llm.strategies.rerank`（`sys_models` tag `RERANKING`）。
- [ ] **Step 3:** `POST /datasets/{id}/hit-testing` body `{query, retrieval_model?}`；写 `dataset_query`；返回 `{query, records: [{segment, score, document}]}`。
- [ ] **Step 4:** `GET /datasets/{id}/queries` 历史列表。
- [ ] **Step 5:** 集成测试：索引样例文档 → hit-testing 返回 ≥1 条。

---

### Task 17: Qdrant + Weaviate 实现

**Files:**
- Create: `backend/app/dataset/infrastructure/vector/qdrant/qdrant_vector.py`
- Create: `backend/app/dataset/infrastructure/vector/weaviate/weaviate_vector.py`
- Modify: `vector_factory.py`, `pyproject.toml`

- [ ] **Step 1:** 移植 Dify `QdrantVectorFactory` / `WeaviateVectorFactory`；env 读 `DATASET_QDRANT_*`, `DATASET_WEAVIATE_*`。
- [ ] **Step 2:** 添加可选依赖 `qdrant-client`, `weaviate-client`。
- [ ] **Step 3:** factory match 分支补全；文档说明切换 `DATASET_VECTOR_STORE` 仅影响新建 collection（已有库读 `index_struct.type`）。

---

## Phase P5 — 前端

### Task 18: 路由与导航迁移

**Files:**
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/layout/AppLayout.tsx`, `AppBreadcrumb.tsx`
- Modify: `frontend/src/features/workspace/OverviewPage.tsx`
- Delete or repurpose: `frontend/src/features/workspace/KnowledgeBasePage.tsx`
- Create: `frontend/src/features/dataset/index.ts`

- [ ] **Step 1:** 路由改为：

```tsx
{ path: 'dataset', element: <DatasetListPage /> },
{
  path: 'dataset/:datasetId',
  element: <DatasetSectionLayout />,
  children: [
    { path: 'documents', element: <DocumentListPage /> },
    { path: 'documents/:documentId', element: <DocumentDetailPage /> },
    { path: 'hit-testing', element: <HitTestingPage /> },
    { path: 'settings', element: <DatasetSettingsPage /> },
  ],
},
```

> 新建知识库 **不** 使用独立路由 `/app/dataset/create`；由列表页全屏 `Modal` 承载向导。向已有库追加文档在详情内以同样 Modal 打开（传入 `datasetId`）。

- [ ] **Step 2:** 全局 `knowledge-base` → `dataset`（Overview 卡片、侧边栏、`nav.dataset` i18n）。
- [ ] **Step 3:** 添加 `/app/knowledge-base` → `/app/dataset` 的 `Navigate` 重定向（兼容旧链接）。

---

### Task 19: API 客户端

**Files:**
- Create: `frontend/src/features/dataset/api/datasets.ts`
- Create: `frontend/src/features/dataset/api/documents.ts`
- Create: `frontend/src/features/dataset/api/segments.ts`
- Create: `frontend/src/features/dataset/api/hitTesting.ts`

- [ ] **Step 1:** 封装 `listDatasets`, `getDataset`, `patchDataset`, `deleteDataset`, `initDataset`, `indexingEstimate`, `getDefaultProcessRule`, `uploadDatasetFile`, `getBatchIndexingStatus` — 使用现有 `apiJson` + `useAuth().workspaceId`。
- [ ] **Step 2:** documents / segments / hitTesting 同理。

---

### Task 20: 知识库列表页（筛选 + 全屏新建）

**Files:**
- Create: `frontend/src/features/dataset/DatasetListPage.tsx`
- Create: `frontend/src/features/dataset/DatasetListPage.css`
- Create: `frontend/src/features/dataset/create/DatasetCreateWizardModal.tsx`

- [ ] **Step 1:** 顶部 inline `Form`（参考 `FileOcrTaskPage` §filter）：`知识库` Input（`name`）、`状态` Select（`indexing_technique`）、`DatePicker.RangePicker`（`create_range`）、**搜索** / **重置**。
- [ ] **Step 2:** 重置右侧增加 **新建知识库** 按钮 → `setCreateOpen(true)`。
- [ ] **Step 3:** `Table` 列：名称、文档数、索引方式 Tag、创建时间；行点击 → `/app/dataset/:id/documents`；删除库 Popconfirm。
- [ ] **Step 4:** `DatasetCreateWizardModal` — `Modal` 全屏：

```tsx
<Modal
  open={createOpen}
  title={t('dataset.create.modalTitle')}
  width="100%"
  style={{ top: 0, maxWidth: '100vw', padding: 0 }}
  styles={{ body: { height: 'calc(100dvh - 110px)', overflow: 'auto', padding: 0 } }}
  footer={null}
  destroyOnHidden
  mask={{ closable: !indexingInProgress }}
  onCancel={() => !indexingInProgress && setCreateOpen(false)}
>
  <DatasetCreateWizard onSuccess={(id) => { setCreateOpen(false); navigate(`/app/dataset/${id}/documents`) }} />
</Modal>
```

- [ ] **Step 5:** `listDatasets` 传 query 与表单同步；搜索时 `page=1`。

---

### Task 21: 创建向导组件（Step 1–3）

**Files:**
- Create: `frontend/src/features/dataset/create/DatasetCreateWizard.tsx`
- Create: `frontend/src/features/dataset/create/StepOneUpload.tsx`
- Create: `frontend/src/features/dataset/create/StepTwoChunking.tsx`
- Create: `frontend/src/features/dataset/create/StepThreeProcessing.tsx`
- Create: `frontend/src/features/dataset/create/WizardStepper.tsx`
- Create: `frontend/src/features/dataset/components/ChunkingSettingsForm.tsx`
- Create: `frontend/src/features/dataset/components/IndexingModeForm.tsx`
- Create: `frontend/src/features/dataset/components/RetrievalSettingsForm.tsx`
- Create: `frontend/src/features/dataset/components/SegmentPreviewPanel.tsx`

- [ ] **Step 1:** `DatasetCreateWizard` props：`datasetId?: string`（有则追加文档，无则 `initDataset` 新建库）、`onSuccess(id)`、`onCancel()`。
- [ ] **Step 2:** `WizardStepper` — Ant Design `Steps` 三步。
- [ ] **Step 3:** StepOne — 仅「导入已有文本」+ `Upload.Dragger`。
- [ ] **Step 4:** StepTwo — 左右分栏 + `indexingEstimate` 预览。
- [ ] **Step 5:** StepThree — 轮询 `getBatchIndexingStatus`；完成后调 `onSuccess`。
- [ ] **Step 6:** `DocumentListPage` 工具栏「追加文档」复用同一 `DatasetCreateWizardModal`，传入 `datasetId`。

---

### Task 22: 详情 Layout + 文档列表

**Files:**
- Create: `frontend/src/features/dataset/layout/DatasetSectionLayout.tsx`
- Create: `frontend/src/features/dataset/documents/DocumentListPage.tsx`
- Create: `frontend/src/features/dataset/documents/DocumentDetailPage.tsx`

- [ ] **Step 1:** Layout — Ant Design `Menu` 或 `Tabs`：文档 / 召回测试 / 设置；顶栏显示库名。
- [ ] **Step 2:** DocumentListPage — 顶部筛选：**文件名**、**状态**、**创建时间**、搜索/重置（无「知识库」项）；`Table` + **操作列**。
- [ ] **Step 3:** DocumentDetailPage — 分段 `Table` + 新增/编辑 Drawer + 删除 Popconfirm。

---

### Task 23: 召回测试与设置页

**Files:**
- Create: `frontend/src/features/dataset/hit-testing/HitTestingPage.tsx`
- Create: `frontend/src/features/dataset/settings/DatasetSettingsPage.tsx`

- [ ] **Step 1:** HitTestingPage — `Input.Search` + 结果 `List` 展示 content/score/文档名；可选折叠「检索参数覆盖」。
- [ ] **Step 2:** SettingsPage — 复用 `ChunkingSettingsForm` + `IndexingModeForm` + `RetrievalSettingsForm`；保存调 `patchDataset`；高质量不可改 economy 时禁用 Radio 并 Tooltip 说明。

---

### Task 24: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1:** 添加 `nav.dataset`、`dataset.list.*`、`dataset.create.*`、`dataset.documents.*`、`dataset.hitTesting.*`、`dataset.settings.*` 键（中英文）。
- [ ] **Step 2:** 移除或保留 `nav.knowledgeBase` 作废弃 alias。

---

## Phase P6 — 收尾

### Task 25: 后端测试与 spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-08-dataset-knowledge-base-design.md` §10 实现对照

- [ ] **Step 1:** 运行 `cd backend; pytest tests/test_dataset_*.py -v`，全部 PASS。
- [ ] **Step 2:** 运行 `cd frontend; npm run build`，无 TS 错误。
- [ ] **Step 3:** 更新 spec §10 实现对照表为实际文件路径与状态「已实现」。

---

## 自检（Plan vs Spec）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 表 `dataset_*` 无 FK | Task 2, 3 |
| 文件上传 Step 1 | Task 5, 21 |
| ExtractProcessor 移植 | Task 6 |
| 通用/父子分段 | Task 7, 21 |
| high_quality / economy | Task 9, 11, 21 |
| Vector 抽象 + pgvector | Task 8 |
| Qdrant / Weaviate | Task 17 |
| Celery 索引 | Task 10 |
| init / indexing-estimate | Task 11 |
| 文档 CRUD + 操作列 | Task 13, 22 |
| 分段 CRUD | Task 14, 22 |
| 召回测试 | Task 16, 23 |
| 设置页 | Task 15, 23 |
| `/app/dataset` 路由 | Task 18 |
| 列表筛选 + 全屏新建 Modal | Task 12, 20, 21 — **P1 列表+Modal 壳已落地** |
| Ant Design UI | Task 20–23 — **列表页 P1 部分** |
| env 同步 | Task 1 |
| Popconfirm 删除 | Task 20, 22 |

**Placeholder 扫描:** 无 TBD/TODO 步骤；每个 Task 有明确文件路径与验证命令。

---

## 执行建议顺序

1. P1 Task 1–5（可并行前端 Task 18 路由壳）
2. P2 Task 6–11（阻塞前端向导）
3. P3 Task 12–15
4. P4 Task 16–17
5. P5 Task 19–24
6. P6 Task 25
