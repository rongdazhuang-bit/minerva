# 知识图谱模块：集成 GraphRAG / LightRAG 可行性与设计

**状态：** 已实现（首期；Worker 真实引擎可选，测试/无 SDK 可用 fake）  
**日期：** 2026-08-23  
**类型：** 可行性分析 + 模块设计（独立于 Dataset）  
**Minerva 约定：** 无库级外键；删除在应用层；二次确认使用 Popconfirm；环境变量同步 `backend/.env.example` 与 `backend/.env.dev`；主内容区布局见 `frontend/docs/LAYOUT.md`

**关联文档：**

- [2026-06-08-dataset-knowledge-base-design.md](./2026-06-08-dataset-knowledge-base-design.md)（现有向量知识库；本模块不修改）
- [2026-06-02-agent-mem0-memory-design.md](./2026-06-02-agent-mem0-memory-design.md)（mem0 Neo4j；本模块不复用）
- [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)

---

## 1. 目标与范围

在 Minerva 新建完全独立的「知识图谱」菜单与后端模块，对 **GraphRAG（Microsoft）** 与 **LightRAG（HKUDS）** 做可落地集成。用户建库时二选一引擎；存储按 `(workspace_id, graph_id)` 隔离；可见性由工作区共享图谱 + 用户级 ACL 控制。

本文件同时给出可行性结论（按小/中/大语料分档）。**不计 LLM token 成本**；规模档位只评估时长、磁盘、并发与运维风险。

### 1.1 包含 / 不包含（首期）

| 包含 | 不包含（首期） |
|------|----------------|
| 独立菜单与 `/app/graph-kb` 路由 | 改现有 Dataset 向量知识库 |
| 建库时选择 GraphRAG **或** LightRAG（不可混挂） | 同一图谱双引擎、检索对比 |
| 独立上传文件 + 粘贴/导入纯文本 | 从 Dataset 选文档导入 |
| 索引进度、问答、实体/关系表格 | Agent 对话检索工具 |
| 交互画布（默认子图，不全量渲染） | 开放对外 Query API |
| 社区报告（GraphRAG）/ 主题与双层摘要（LightRAG） | GraphRAG 增量索引 |
| workspace 成员 ACL + admin 总览 + 超管无限制 | 独立的跨 workspace 总览页（超管靠切换当前 workspace） |
| 独立引擎 Worker（主 API 不 import SDK） | 与 mem0 Neo4j 共用图库 |

### 1.2 已确认决策

| 项 | 决策 |
|----|------|
| 产品形态 | 新建独立模块与菜单，不扩展 Dataset |
| 引擎策略 | 创建时二选一；创建后引擎字段只读 |
| 隔离 | 存储 `(workspace_id, graph_id)`；用户可见性走 ACL |
| ACL | `only_me` / `partial_members` / `all_team_members` |
| workspace admin | 可见并管理**本 workspace 全部**图谱 |
| 超管 | **不受权限限制**，可见并管理全部图谱（与 Gateway「全平台数据」一致；UI 仍跟当前 workspace） |
| 消费方 | 仅新菜单（建图、浏览、问答）；首期不接 Agent、不开对外 API |
| 数据来源 | 独立文件上传 + 纯文本粘贴/导入 |
| 模型 | Chat / Embedding 在 **Worker 进程环境变量** 配置（`GRAPH_KB_LLM_*` / `GRAPH_KB_EMBEDDING_*`）；图谱行与 API 不传模型凭证 |
| 浏览 | 表格 + 交互画布 + 社区/主题摘要 |
| 架构 | **方案 1**：Minerva GraphKB + 独立 LightRAG Worker + 独立 GraphRAG Worker |
| Token | 不计消耗；不因费用裁剪 GraphRAG |
| 规模 | 可行性按小 / 中 / 大三档分别评估 |

### 1.3 架构方案（已选）

**采用方案 1（Worker 隔离）。** 不在主 API / 主 Celery 进程 `import lightrag` 或 `graphrag`。不自研替代两套引擎（方案 3）；不同进程同 venv 直接双 SDK（方案 2）因依赖冲突与内存风险否决。

---

## 2. 可行性结论

### 2.1 引擎能力对照

| 维度 | LightRAG | GraphRAG |
|------|----------|----------|
| 多租户 | 原生 `workspace` 参数；初始化后不可改；须一图谱一实例 | **无官方多租户**；社区讨论无结论；仓库处于 maintenance mode |
| 存储隔离 | PG 表内 `workspace` 字段 / Neo4j label / 文件子目录 | 仅能靠独立 `--root` 目录（silo） |
| 增量 | 支持 `ainsert` | 不成熟；首期只做全量重建 |
| 摘要 | 实体局部 + 主题全局（双层检索） | 社区检测 + 层级社区报告（强项） |
| 集成风险 | 实例与连接池若做成全局单例会串 workspace | 依赖重、停更、产物为目录级 parquet/向量 |

**结论：** 两套都可以进独立菜单，前提是 Minerva **自建 ACL 与 namespace**，并且 **进程隔离**。不能依赖 GraphRAG 做租户隔离；LightRAG 的 `workspace` 只能作为存储分桶，不能替代 Minerva 鉴权。

### 2.2 分档（不计 token）

| 档 | 语料 | LightRAG | GraphRAG | 产品含义 |
|----|------|----------|----------|----------|
| 小 | 数十份文档，合计 < 5 万字 | 可行，增量友好 | 可行，全量即可 | 两套都能进菜单 |
| 中 | 上百份，合计 5–50 万字 | 可行，必须异步 + PG workspace | 可行但索引长、root 变大 | 必须走方案 1，禁止同步堵 API |
| 大 | 上千份或百万字以上 | 可行；Worker 内须按图谱做实例 LRU/TTL，避免每请求冷启动 | 磁盘与耗时是主风险；须限并发、可取消、画布强制子图 | 可做，需运维配额 |

### 2.3 总评与主要风险

独立菜单 + 方案 1 **可行**。隔离由「Minerva ACL + `(workspace_id, graph_id)` namespace」保证。

| 风险 | 缓解 |
|------|------|
| GraphRAG 停更、依赖漂移 | 钉版本；Worker 独立 venv；适配器接口稳定，可日后替换实现 |
| 双引擎依赖冲突 | 主 API 不安装两套 SDK；两个 Worker 各用各的 venv/镜像 |
| LightRAG 全局连接池串 workspace | 按 `kg_{workspace_id}_{graph_id}` 建实例；禁止改已有实例的 workspace |
| 大图画布卡死 | 默认 1–2 跳子图 / 社区内子图 / 检索命中实体，禁止首屏全图 |
| 与 mem0 Neo4j 串数据 | LightRAG 使用独立 PostgreSQL schema 或独立库，不复用 `MEM0_NEO4J_*` |
| 删除后引擎残留 | DELETE 同步掉业务行；Celery 异步 `delete_namespace`，失败可重试，不挡列表消失 |

---

## 3. 总体架构

```
前端 /app/graph-kb
        │
        ▼
Minerva API  app/graph_kb
  · PermissionGateway + 图谱 ACL
  · 元数据 / 成员 / 文档 / 任务
        │
        ├─ Celery queue=graph_kb   （编排：投递、超时、状态、异步清理）
        │
        ├─ LightRAG Worker（独立 venv / 进程）
        │     workspace = kg_{workspace_id}_{graph_id}
        │     存储：独立 PostgreSQL（KV / 向量 / 图 / doc status）
        │
        └─ GraphRAG Worker（独立 venv / 进程或 CLI）
              root = {GRAPH_KB_DATA}/{workspace_id}/{graph_id}/
```

### 3.1 职责边界

**Minerva 拥有：** 图谱元数据、ACL、源文件与纯文本、索引任务状态、问答历史、画布/表格用的只读投影（实体、关系、社区/主题摘要）。

**引擎拥有：** 各自的索引产物与检索引擎。Minerva 只通过适配器调用 `index` / `query` / `export_graph` / `list_summaries` / `delete_namespace`，不直接读写 LightRAG 内部表或 GraphRAG parquet。

**主 API 禁止** `import lightrag` / `import graphrag`。Celery 编排进程同样不加载引擎 SDK；只向 Worker 发任务。

### 3.2 隔离规则

| 层 | 规则 |
|----|------|
| 存储 | 引擎 namespace = `(workspace_id, graph_id)`；禁止跨图谱复用实例 |
| 访问 | API 先判定身份与 ACL，再把该图谱的 id 传给 Worker |
| Namespace 拼接 | **仅 Worker** 使用 `workspace_id` + `graph_id` 拼接；主 API 不传可被改写的自由字符串 |
| 用户 | 不按 `user_id` 分存储；「仅自己 / 指定成员 / 全员」只在 Minerva 判定 |
| 进程 | 主 API 与两套引擎进程分离 |
| 与 Dataset | 无表共享、无向量 collection 共享、无导入通道（首期） |
| 与 mem0 | 不使用 `MEM0_NEO4J_*`；LightRAG 用 `GRAPH_KB_LIGHTRAG_*` 独立连接 |

LightRAG workspace 字面量固定为：

```text
kg_{workspace_id}_{graph_id}
```

其中 UUID 去掉连字符、小写。GraphRAG root 固定为：

```text
{GRAPH_KB_DATA}/{workspace_id}/{graph_id}/
```

`GRAPH_KB_DATA` 必须落在 Minerva 数据目录内，禁止用户指定任意路径。

### 3.3 模型配置（Worker 环境变量）

Chat 与 Embeddings 的 OpenAI-compatible `base_url`、`api_key`、`model` **不在** `graph_kb` 表、REST 请求体或 Worker HTTP 入参中传递。各 Worker 在启动时从本目录 `.env.<WORKER_ENV>` 读取：

| 变量 | 说明 |
|------|------|
| `GRAPH_KB_LLM_BASE_URL` | Chat API 基址 |
| `GRAPH_KB_LLM_API_KEY` | Chat API Key |
| `GRAPH_KB_LLM_MODEL` | Chat 模型名 |
| `GRAPH_KB_EMBEDDING_BASE_URL` | Embeddings API 基址 |
| `GRAPH_KB_EMBEDDING_API_KEY` | Embeddings API Key |
| `GRAPH_KB_EMBEDDING_MODEL` | Embeddings 模型名 |

`GRAPH_KB_WORKER_FAKE=1` 时可不填上述变量。日志与 `graph_kb_job.error` 禁止写明文 key（脱敏为后四位或省略）。

主 API 仅通过 Bearer Key 调用 Worker；**不**解析 `sys_models` 为 GraphKB 索引/查询传凭证。

---

## 4. 权限与 ACL

功能码：`feature:graph_kb`（租户 entitlement + 角色授权，对齐 Dataset 的 `feature:dataset`）。

### 4.1 判定顺序

1. **超管**（`sys_user.is_super_admin = true`）：绕过 feature、workspace 成员、图谱 ACL；可见并管理全部图谱。列表 UI 仍使用当前 JWT `wid` 作为默认空间；切换 workspace 即看到该空间全部图谱。不做首期「全平台一张表」总览页。
2. 未开通 `feature:graph_kb` → 403。
3. 非本 workspace 成员 → 403。
4. **workspace admin**：可见并管理**本 workspace 全部**图谱（列表、浏览、问答、改 ACL、删库、重跑索引）。不写入 `graph_kb_member`。
5. **普通成员：**
   - `all_team_members`：本 workspace 成员可见可问。
   - `only_me`：仅 `created_by`。
   - `partial_members`：`created_by` ∪ `graph_kb_member.user_id`。
6. 普通成员不能改他人 ACL、不能删除他人图谱；**创建者**可管理自己的库（含改权限、删库、重跑索引）。

未授权访问单库时返回 **404**（不暴露存在性）。超管除外。

### 4.2 列表过滤

| 身份 | 列表 |
|------|------|
| 超管 | 当前 workspace 下全部图谱 |
| workspace admin | 本 workspace 全部图谱；可筛「仅我的 / 全部」 |
| 成员 | 仅 ACL 允许的图谱 |

`permission` 只约束成员可见性；admin / 超管总览不依赖成员表。

---

## 5. 数据模型

表前缀 `graph_kb`。无 `FOREIGN KEY` / `ON DELETE CASCADE`；关联列为 UUID + 索引；逻辑引用在注释中说明。删除顺序在 service 层实现。

### 5.1 `graph_kb`

| 列 | 说明 |
|----|------|
| `id` | uuid PK |
| `workspace_id` | uuid NOT NULL，索引 |
| `name` | varchar(255) NOT NULL |
| `description` | text NULL |
| `engine` | `graphrag` \| `lightrag`，创建后不可改 |
| `permission` | `only_me` \| `partial_members` \| `all_team_members` |
| `indexing_status` | `empty` \| `pending` \| `running` \| `completed` \| `failed` |
| `created_by` / `updated_by` | uuid |
| `create_at` / `update_at` | timestamptz |

### 5.2 `graph_kb_member`

`permission = partial_members` 的成员。列：`id`、`workspace_id`、`graph_id`、`user_id`、`created_by`、`create_at`。唯一约束 `(graph_id, user_id)`。

### 5.3 `graph_kb_document`

| 列 | 说明 |
|----|------|
| `id`、`workspace_id`、`graph_id` | 标识 |
| `source_type` | `upload_file` \| `plain_text` |
| `name` | 文件名或文本标题 |
| `storage_key` | 上传文件对象键；纯文本可为 NULL |
| `text_content` | 短文本可直接存；超长纯文本改为对象存储，本列留预览截断 |
| `mime_type` / `size_bytes` | 文件元数据 |
| `indexing_status` / `error` | 文档级状态 |
| `created_by`、`create_at` | 审计 |

首期文件类型与 Dataset 常用类型对齐：`txt`、`md`、`pdf`、`docx`、`html`、`csv`。不做 OCR、不做扫描件。

纯文本超长阈值：超过 `GRAPH_KB_INLINE_TEXT_MAX_CHARS`（默认 20000）写入对象存储，`text_content` 只保留截断预览。

### 5.4 `graph_kb_job`

索引或清理任务：`graph_id`、`workspace_id`、`kind`（`index` \| `reindex` \| `cleanup`）、`status`、`error`、`started_at`、`finished_at`、`created_by`。同一图谱同一时刻只允许一个 `index` / `reindex` 为 `pending` 或 `running`；冲突返回 409。

### 5.5 `graph_kb_query`

菜单内问答历史：`graph_id`、`workspace_id`、`query`、`mode`、`answer`、`created_by`、`create_at`。引用实体/摘要 id 以 jsonb 存放。

### 5.6 只读投影

索引成功后由 Worker `export_graph` / `list_summaries` 回写，供表格、画布、摘要页。**不替代**引擎存储。

| 表 | 说明 |
|----|------|
| `graph_kb_entity` | `graph_id`、`workspace_id`、引擎侧 entity id、名称、类型、描述、community_id 可选 |
| `graph_kb_relation` | `graph_id`、`workspace_id`、from/to entity id、关系类型、描述、权重 |
| `graph_kb_community` | `graph_id`、`workspace_id`、社区/主题 id、标题、摘要、层级、parent_id |

失败的 job **不覆盖**上一份已成功投影。

### 5.7 应用层删除顺序

**同步（DELETE API，同一事务）：**  
`graph_kb_query` → `graph_kb_community` → `graph_kb_relation` → `graph_kb_entity` → `graph_kb_job` → `graph_kb_document` 行 → `graph_kb_member` → `graph_kb`。该图谱全部 job 一并删除，不留审计孤儿行。

**异步（Celery `graph_kb.cleanup`）：**  
源文件对象存储 + Worker `delete_namespace`（LightRAG 清 workspace；GraphRAG 删除 root 目录）。外部清理失败不阻断 DELETE API，job 可重试。

删除用户或成员时 **不** 级联删除图谱。`created_by` / 成员 `user_id` 可成孤儿；列表显示「未知用户」，由 workspace admin 或超管接管（改 ACL 或删除图谱）。

---

## 6. 索引流水线与 Worker 适配

### 6.1 流程

1. 创建 `graph_kb`（引擎、权限）。
2. 写入 `graph_kb_document`（文件和/或纯文本）。
3. 入队 `graph_kb_job(kind=index|reindex, status=pending)`。
4. Celery `queue=graph_kb`：调用对应 Worker（Worker 使用进程内已配置的 Chat/Embeddings）。
5. 成功：`export_graph` + `list_summaries` 写入投影；`indexing_status=completed`。
6. 失败：`job=failed`，保留上一份投影；文档标 error。

Worker 未配置模型且非 fake 模式时，索引/查询在 Worker 侧失败；主 API 映射为 502/503，不建「模型缺失」类 400。

### 6.2 统一 Worker 接口

| 方法 | 含义 |
|------|------|
| `index` | 建图。LightRAG：增量插入新文档；GraphRAG：全量重建 |
| `query` | 问答/召回 |
| `export_graph` | 实体与关系 |
| `list_summaries` | GraphRAG 社区报告；LightRAG 主题/高层实体摘要 |
| `delete_namespace` | 删除该图谱引擎数据 |

所有方法入参必须包含 `workspace_id`、`graph_id`。Worker 内部拼接 namespace，拒绝调用方传入的任意 workspace 字符串。

### 6.3 引擎差异

| | LightRAG | GraphRAG |
|--|----------|----------|
| Namespace | `kg_{workspace_id}_{graph_id}` | `{GRAPH_KB_DATA}/{workspace_id}/{graph_id}/` |
| 存储 | 独立 PostgreSQL | 目录 silo（input + output） |
| 追加文档 | 增量 `ainsert` | 写入 input 后全量重建 |
| 取消 | 协作取消 + 超时 | revoke 后允许残留目录，重跑覆盖 |

超时由 `GRAPH_KB_JOB_TIMEOUT_SECONDS` 配置，大库可调高。超时将 job 标 failed；GraphRAG 不自动删除已写磁盘，允许重跑全量。

暂停/取消：Celery revoke + Worker 协作取消。已部分写入以 job 终态为准，失败不回滚上一份投影。

---

## 7. 检索、画布与前端

### 7.1 查询 API

`POST /api/workspaces/{workspace_id}/graph-kbs/{graph_id}/query`

请求：`query`、`mode`、可选 `top_k`。写入 `graph_kb_query`。

| 统一 `mode` | GraphRAG | LightRAG |
|-------------|----------|----------|
| `local` | local search | local |
| `global` | global search（社区报告） | global |
| `hybrid` | 本地+全局；引擎无组合则降级为 `global` | hybrid |
| `naive` | 引擎无此模式则 **400** | naive |
| `basic` | Basic Search（text units 向量 RAG） | **400** |

| HTTP | 条件 |
|------|------|
| 404 | 无 ACL（超管除外） |
| 400 | `naive` 用于 GraphRAG；`basic` 用于 LightRAG；引擎字段与 Worker 不匹配 |
| 409 | `indexing_status` 不是 `completed` |
| 503 | Worker 不可达；投影与列表仍可读 |
| 200 | 无命中时仍 200，答案可空，引用为空数组 |

### 7.2 浏览

投影只读，不在请求路径扫描引擎磁盘。

- **表格：** 实体、关系分页（默认每页 10，对齐仓库分页常量），可按名称/类型筛选。
- **画布：** 默认不渲染全图。入口为「问答命中实体 / 选中实体 1–2 跳 / 社区内子图」。点选节点展示属性与邻居。
- **摘要：** GraphRAG 展示社区报告树；LightRAG 展示主题/高层实体。点击摘要定位子图。

画布库在实现计划中选定（须满足 4px 容器圆角、页内滚动，不撑破 `.minerva-app-main-frame`）。本 spec 不绑定具体 npm 包。

### 7.3 前端信息架构

| 路径 | 页面 |
|------|------|
| `/app/graph-kb` | 列表 |
| `/app/graph-kb/create` | 新建：引擎、权限、首批文件/文本 |
| `/app/graph-kb/:id/documents` | 文档、上传/粘贴、索引进度 |
| `/app/graph-kb/:id/graph` | 表格 + 画布 |
| `/app/graph-kb/:id/summaries` | 社区/主题摘要 |
| `/app/graph-kb/:id/qa` | 问答 |
| `/app/graph-kb/:id/settings` | 名称、ACL、成员；引擎只读 |

前端目录：`frontend/src/features/graph-kb/`。  
后端目录：`backend/app/graph_kb/`。  
详情页左侧 Tab，对齐 Dataset 的 `DatasetSectionLayout`。  
删除图谱/文档使用 Ant Design `Popconfirm`，禁止 `Modal.confirm`。  
布局：主内容区 4px 圆角、3px 边距、外框包裹、页内滚动。

菜单：与「知识库」平级的新项，i18n 键建议 `nav.graphKb`；权限码 `feature:graph_kb`。须在 `sys_permission` / 菜单种子中新增，并同步租户 entitlement 目录。

### 7.4 REST 清单（前缀 `/api/workspaces/{workspace_id}`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/graph-kbs` | 分页列表（ACL / admin / 超管过滤） |
| POST | `/graph-kbs` | 创建空图谱 |
| GET | `/graph-kbs/{id}` | 详情 |
| PATCH | `/graph-kbs/{id}` | 名称、描述、permission、成员；不可改 `engine` |
| DELETE | `/graph-kbs/{id}` | 同步删库 + 异步清理 |
| POST | `/graph-kbs/{id}/documents/upload` | 上传文件 |
| POST | `/graph-kbs/{id}/documents/text` | 导入纯文本 |
| GET | `/graph-kbs/{id}/documents` | 文档分页 |
| DELETE | `/graph-kbs/{id}/documents/{doc_id}` | 同步删文档行与对象；若图谱已完成或失败过索引，自动入队 `reindex`。LightRAG：按「仍存在的文档」同步引擎（去掉已删 doc）。GraphRAG：全量重建。已有 running job 时文档仍删，reindex 返回 409，调用方稍后 `POST .../index` |
| POST | `/graph-kbs/{id}/index` | 入队建图/重建 |
| GET | `/graph-kbs/{id}/jobs/{job_id}` | 任务状态 |
| GET | `/graph-kbs/{id}/entities` | 投影分页 |
| GET | `/graph-kbs/{id}/relations` | 投影分页 |
| GET | `/graph-kbs/{id}/graph-view` | 子图：`seed_entity_id` + `hops`（1 或 2）或 `community_id` |
| GET | `/graph-kbs/{id}/summaries` | 社区/主题 |
| POST | `/graph-kbs/{id}/query` | 问答 |
| GET | `/graph-kbs/{id}/queries` | 问答历史 |

鉴权依赖：`make_require_feature_workspace(FEATURE_GRAPH_KB)`，再叠加 §4 ACL。

---

## 8. 错误处理（补充）

| 场景 | 行为 |
|------|------|
| 重复 index | 409 |
| Worker 宕机 | 查询 503；投影只读仍 200 |
| 文件类型不支持 | 上传 400 |
| 用户已删但仍在 member | 列表显示未知用户，不影响 admin 访问 |

---

## 9. 测试

| 类型 | 范围 |
|------|------|
| 单测 | ACL（成员 / 创建者 / admin / 超管）、namespace 拼接、mode 映射、删除顺序、列表过滤 |
| 合约测 | Worker 接口 mock，不启动真实引擎 |
| 集成（可选） | 小语料各引擎一条黄金路径：建库 → 索引 → query → export |
| 隔离断言 | 两个 workspace、两个用户交叉 query；投影与答案不得串库 |

隔离测试必须覆盖：workspace A 的图谱 id 不得被 workspace B 的成员用 URL 猜到后 200；`only_me` 图谱对同空间其他成员 404；admin / 超管为 200。

---

## 10. 环境变量

实现时新增并同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`：

| 变量 | 说明 |
|------|------|
| `GRAPH_KB_DATA` | GraphRAG / 文档落盘根；空则 `backend/data/graph_kb`。Worker 启动脚本可传入该可选环境变量 |
| `GRAPH_KB_LIGHTRAG_DATABASE_URL` | LightRAG 独立 PG；禁止复用 `MEM0_DATABASE_URL` |
| `GRAPH_KB_JOB_TIMEOUT_SECONDS` | 索引超时 |
| `GRAPH_KB_INLINE_TEXT_MAX_CHARS` | 纯文本内联上限，默认 20000 |
| `GRAPH_KB_LIGHTRAG_WORKER_URL` | LightRAG Worker 本机地址 |
| `GRAPH_KB_GRAPHRAG_WORKER_URL` | GraphRAG Worker 本机地址 |
| `GRAPH_KB_LIGHTRAG_WORKER_API_KEY` / `GRAPH_KB_GRAPHRAG_WORKER_API_KEY` | 主 API 调用 Worker 的 Bearer Key（`http` 模式必填） |
| `MINERVA_CELERY_QUEUES` | Worker 须包含 `graph_kb`（实现时回填脚本说明） |

**Worker 进程（`backend/workers/graph-kb-*/.env.<WORKER_ENV>`，非 fake 时必填）：**  
`GRAPH_KB_LLM_BASE_URL`、`GRAPH_KB_LLM_API_KEY`、`GRAPH_KB_LLM_MODEL`、  
`GRAPH_KB_EMBEDDING_BASE_URL`、`GRAPH_KB_EMBEDDING_API_KEY`、`GRAPH_KB_EMBEDDING_MODEL`。

密钥类值不写入 `.env.example` 明文生产密钥。

---

## 11. 实现对照（以代码为准，2026-08-23）

| spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| 独立 GraphKB 模块 | `backend/app/graph_kb/`（`api/` `domain/` `engine/` `service/` `task/`） | CRUD / 文档 / 索引 / 查询 / 投影已落地 |
| `GraphEngineClient` / Fake / HTTP | `engine/protocol.py`、`fake_client.py`、`http_client.py`、`factory.py` | `GRAPH_KB_ENGINE_CLIENT=fake` 用 Fake；默认 `http` |
| Fake 隔离 key | `FakeGraphEngineClient._store[(workspace_id, graph_id)]` | 交叉 workspace 回归见 `tests/test_graph_kb_engine_client.py` |
| LightRAG Worker | `backend/workers/graph-kb-lightrag/`；脚本 `scripts/run-graph-kb-lightrag-worker.cmd`（`:8101`） | `GRAPH_KB_WORKER_FAKE=1` 可跳过 SDK；`delete_namespace` 缓存未命中仍打开并清空；reindex 先 wipe 再写入当前文档 |
| GraphRAG Worker | `backend/workers/graph-kb-graphrag/`；脚本 `scripts/run-graph-kb-graphrag-worker.cmd`（`:8102`） | 禁止请求体带 `root`；reindex 先清空 `input/`/`output/`；真实 index 从 Worker env 写 `settings.yaml` |
| `feature:graph_kb` 菜单与权限 | `backend/app/core/security/permission_codes.py` + SQL seeds；前端 `frontend/src/features/graph-kb/`、`/app/graph-kb` | 独立菜单；与 Dataset 分离 |
| ACL（only_me / partial / all_team；admin 本区；超管无限制） | `domain/acl.py`；列表过滤 service | `GraphAclActor`；隔离回归见 `tests/test_graph_kb_isolation.py` |
| 本模块表（无库级外键） | `backend/sql/schema_postgresql.sql`；ORM `domain/db/models.py` | 删除在应用层 |
| 文件 + 纯文本入库 | `service/document_service.py` + `api/router.py` | `GRAPH_KB_INLINE_TEXT_MAX_CHARS` |
| Worker 侧 Chat/Embeddings | `backend/workers/graph-kb-*/app/config.py`；`GRAPH_KB_LLM_*` / `GRAPH_KB_EMBEDDING_*` | 已删除 `model_resolver.py`；HTTP index/query **不传** `llm`/`embedding` |
| Celery `graph_kb` 队列 | `task/index_task.py`、`task/cleanup_task.py`；`MINERVA_CELERY_QUEUES` 含 `graph_kb` | 索引冲突 409；超时 `GRAPH_KB_JOB_TIMEOUT_SECONDS`；`send_task` 失败会把 job 标 failed（避免一直 409） |
| 投影回写 / 失败保留旧投影 | `service/index_service.py`、`projection_service.py` | 先 commit `running`+`started_at` 再调 Worker；失败 rollback 后回写 started_at/failed/finished_at/error |
| query mode 映射、409/503 | `engine/modes.py`、`service/query_service.py`、`engine/http_client.py` | GraphRAG 拒 `naive`、接受 `basic`；LightRAG 拒 `basic`；未就绪 409；query POST **不含**模型凭证 |
| 表格 + 子图画布 + 摘要 | `view_service.py`；前端 `graph/` `summaries/` `qa/` | `graph-view` hops 1\|2、最多 200 节点 |
| 删除顺序 + 异步 cleanup | `deletion_service.py`、`cleanup_service.py` | 文档：commit 后再 unlink；删图谱后入队 cleanup |
| 不复用 mem0 Neo4j | `GRAPH_KB_LIGHTRAG_DATABASE_URL` / `GRAPH_KB_DATA` | 禁止复用 `MEM0_*`；`GRAPH_KB_DATA` 空则 `backend/data/graph_kb` |
| 首期不做 | — | Agent 工具 / 开放 API / Dataset 导入 / GraphRAG 增量 |

Dataset（`backend/app/dataset/`）与 mem0 Neo4j 不在本模块改动范围内。

---

## 12. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-23 | 初稿：可行性 + 方案 1 设计；独立菜单；ACL；admin 总览；超管无限制 |
| 2026-08-23 | Task 8：Celery `graph_kb` 索引/清理、投影回写、`MINERVA_CELERY_QUEUES` 默认含 `graph_kb` |
| 2026-08-23 | Task 8 评审修复：索引失败 rollback 保留旧投影；文档删除 commit 后再 unlink |
| 2026-08-23 | Task 9：query / entities / relations / summaries / graph-view；补 POST index 与 GET job |
| 2026-08-23 | Task 15：§11 回填真实路径；状态改为已实现（首期）；交叉 workspace 隔离回归；README 知识图谱节 |
| 2026-08-23 | 全分支评审修复：query 传模型凭证；delete_namespace 不因缓存未命中提前返回；reindex 丢掉已删文档；GraphRAG 写 settings.yaml；index job 先 commit running；enqueue 失败标 failed；隔离测试；`GRAPH_KB_DATA` 默认 `backend/data/graph_kb` |
| 2026-08-25 | **废止** 图谱级 `llm_model*` / `embedding_model*` 与 `model_resolver`；模型改 Worker env；SQL patch `2026-08-25-graph-kb-drop-model-columns.sql`；API/前端不再选模型 |
| 2026-08-25 | GraphRAG 统一 mode `basic` → Basic Search；`naive` 仍仅 LightRAG；见 `2026-08-25-graph-kb-graphrag-basic-search-design.md` |
