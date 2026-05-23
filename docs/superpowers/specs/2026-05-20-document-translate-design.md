# 多格式文档翻译（段落级 + 保版式 + OCR 扫描 PDF）设计说明

**日期**：2026-05-20  
**状态**：已实现（2026-05-20；UI 重构 2026-05-21 见 `docs/superpowers/specs/2026-05-21-document-translate-ui-refresh-design.md`）  
**范围**：工作区「文档翻译 → 翻译」：支持 Word（DOC / DOCX）/ PDF / TXT / MD / CSV / Excel（XLS / XLSX）；上传区选择源/目标语言与 `model_type=translate` 模型；后台 `backend/app/translate/`；前端 `minerva-ui/src/features/translate/`；**表格列表 + 顶部筛选**；**上传 Modal**；**全屏详情 Modal** 内左右段落对照 + 译文下载；扫描 PDF 自动走现有 `file_ocr` 后再段落翻译；按文件后缀策略模式独立实现；单条 Celery 流水线；首期进度 HTTP 轮询。

---

## 1. 目标与成功标准

### 1.1 目标

- **统一段落中间模型**：各格式策略将文档抽取为有序段落列表，逐段调用翻译模型，再按 `anchor_json` 写回目标文件，尽量保持原排版。
- **一条任务一条历史**：`doc_translate_job` 对应侧栏一项；段落明细存 `doc_translate_segment`。
- **模型**：仅允许工作区 `sys_models` 中 `model_type` 字典 code 为 **`translate`**、已启用且具备有效 `endpoint_url` + `api_key` 的记录。
- **语言**：每次任务在上传区选择 **源语言 + 目标语言**（字典 code，与模型配置解耦）。
- **扫描 PDF**：检测为扫描件（无有效文字层或字符密度过低）时，自动创建并等待 `ocr_file` 完成，再将 OCR 块映射为段落后翻译。
- **交付**：主区 **左右对照**（原文段落 | 译文段落）+ **译文文件下载**（与原扩展名一致）。
- **架构**：方案 A — 统一段落模型 + **单 Celery 任务** 内顺序执行（OCR 等待 → 抽取 → 翻译 → 组装 → 上传结果），不按阶段拆多队列。

### 1.2 成功标准

- 用户上传当前支持后缀（`doc`, `docx`, `pdf`, `txt`, `md`, `csv`, `xls`, `xlsx`）之一，选择语言与 translate 模型后，任务进入异步处理；侧栏可见历史，选中后对照区随轮询刷新段落与进度。
- 任务 `SUCCESS` 后可下载译文；对照区展示全部段落的原文与译文（上限见 §6）。
- Word（DOC / DOCX）/ PDF 下载文件在肉眼可接受范围内保持版式；TXT / MD / CSV / Excel（XLS / XLSX）保持原有结构（换行、表格行列）。
- 扫描 PDF 在配置可用 OCR 工具时自动 OCR，无需用户跳转 OCR 模块手动建任务。
- 数据库表 **无外键、无 ON DELETE 级联**；删除任务在业务层清理子表与 S3 对象。

### 1.3 非目标（首期不做）

- SSE 推送任务进度（二期可对齐 agent）。
- 单段失败后仅重试失败段（首期任一段失败则任务 `FAILED`）。
- 删除 `doc_translate_job` 时自动删除关联 `ocr_file`（仅解除逻辑关联，OCR 记录保留）。
- 浏览器内嵌渲染 PDF/Word 原版式预览（对照区仅为文本段落）。

---

## 2. 模块与目录

### 2.1 后端 `backend/app/translate/`

```text
backend/app/translate/
  api/
    router.py              # FastAPI 路由
    schemas.py             # 请求/响应 DTO
  domain/
    db/
      models.py            # doc_translate_job, doc_translate_segment
    constants.py           # 状态枚举、后缀白名单、Celery 任务名
  service/
    strategies/
      base.py              # DocTranslateFormatStrategy 抽象
      registry.py          # 按后缀解析策略
      txt.py, md.py, csv.py, xls_strategy.py, xlsx.py, word_strategy.py, docx.py, pdf.py
    job_service.py         # 创建/列表/详情/删除/下载
    segment_service.py     # 段落查询
    translate_llm.py       # 单段调用 app/llm（加载 sys_models）
    ocr_bridge.py          # 扫描 PDF：创建 ocr_file、轮询等待 SUCCESS
    run_pipeline.py        # Worker 内流水线编排
  task/
    run_job.py             # Celery shared_task
  infrastructure/
    repository.py          # ORM 访问、offset 分页与筛选计数
```

在 `app/core/api/router.py` 注册 `translate` 路由。

### 2.2 前端

```text
minerva-ui/src/features/translate/
  TranslatePage.tsx          # 主页面（布局对齐 AgentsPage）
  TranslatePage.css
  translateJobUi.ts          # 侧栏标题、日期格式化等
  index.ts
minerva-ui/src/api/translate.ts
```

- 路由：`/app/translate`（替换现有 `/app/doc-translate/translate`）。
- 删除 `features/doc-translate/` 占位实现。
- `AppLayout.tsx` / `AppBreadcrumb.tsx` / `router.tsx` / i18n 路径同步。

### 2.3 依赖库（实现阶段引入，写入 `backend/pyproject.toml`）

| 格式 | 建议库 |
|------|--------|
| docx | `python-docx` |
| doc | LibreOffice 转 DOCX 后复用 Word 策略 |
| xls | legacy xls 策略依赖当前运行环境支持 |
| xlsx | `openpyxl` |
| pdf（文本层） | `pymupdf` 或 `pdfplumber` |
| pdf（写回） | PyMuPDF 文本替换 / 增量层（尽力保留版式） |
| csv | 标准库 `csv` |
| txt/md | 标准库 |

---

## 3. 数据模型

> 约定：所有关联字段为 UUID **无 FK**；索引仅用于查询；删除顺序在 service 显式实现（见 §8）。

### 3.1 `doc_translate_job`

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `workspace_id` | UUID, index | 工作区 |
| `created_by` | UUID, index, nullable | 发起人 |
| `title` | varchar(256) | 侧栏展示，默认 `file_name` |
| `file_name` | varchar(256) | 原始文件名 |
| `file_ext` | varchar(16) | 规范化小写后缀（如 `docx`） |
| `source_lang` | varchar(32) | 源语言字典 code |
| `target_lang` | varchar(32) | 目标语言字典 code |
| `model_id` | UUID, index | `sys_models.id`，业务校验 translate + enabled |
| `status` | varchar(32) | 见 §4.1 |
| `source_object_key` | varchar(1024) | S3 源文件 |
| `result_object_key` | varchar(1024), nullable | S3 译文 |
| `ocr_file_id` | UUID, nullable, index | 逻辑关联 `ocr_file.id` |
| `progress` | smallint | 0–100 |
| `segment_total` | int | 总段落数 |
| `segment_done` | int | 已完成段落数 |
| `error_code` | varchar(64), nullable | |
| `error_message` | text, nullable | |
| `create_at` | timestamptz | |
| `update_at` | timestamptz | |

**索引**：`(workspace_id, update_at DESC, id DESC)` — 支持列表按工作区与更新时间排序筛选；列表响应使用 offset 分页并返回 `{ items, total }`。

### 3.2 `doc_translate_segment`

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `job_id` | UUID, index | 逻辑关联 `doc_translate_job.id` |
| `workspace_id` | UUID, index | 冗余，便于按工作区审计 |
| `seq` | int | 段落序号，从 0 起连续 |
| `source_text` | text | 原文 |
| `translated_text` | text, nullable | 译文 |
| `status` | varchar(16) | `PENDING` / `DONE` / `FAILED` |
| `anchor_json` | jsonb, nullable | 策略写回锚点（run、cell、pdf bbox 等） |
| `error_message` | text, nullable | 单段失败信息 |

**唯一约束（业务层保证）**：同一 `job_id` 下 `seq` 不重复。  
**索引**：`(job_id, seq)`。

### 3.3 SQL 与 ORM

- 在 `backend/sql/schema_postgresql.sql` 追加建表（无 FK）。
- ORM 置于 `translate/domain/db/models.py`，纳入 `create_missing_tables` 引导。

---

## 4. 任务状态机与 Celery 流水线

### 4.1 `doc_translate_job.status`

| 状态 | 含义 |
|------|------|
| `PENDING` | 已创建，待 Worker 领取 |
| `OCR_RUNNING` | 扫描 PDF，等待 `ocr_file` 完成 |
| `EXTRACTING` | 策略抽取段落 |
| `TRANSLATING` | 按段调用模型 |
| `ASSEMBLING` | 写回文件并上传 S3 |
| `SUCCESS` | 完成 |
| `FAILED` | 失败（含 OCR/抽取/翻译/组装任一步） |

`progress` 在 `TRANSLATING` 阶段按 `segment_done / segment_total` 计算（0–100）。

### 4.2 Celery 任务

- 任务名：`translate.run_job`（常量 `DOC_TRANSLATE_RUN_TASK_NAME`）。
- 入参：`job_id`（**必须**为 `doc_translate_job.id` 的 UUID 字符串；**禁止**随机生成或 demo 占位符 `minerva`）。上传 API 创建任务后 `enqueue_task(..., args=[str(row.id)])` 自动入队；若在 `sys_celery` 配置周期/立即执行，须从文档翻译列表复制真实任务 id 填入 `args_json[0]` 或 `kwargs_json.job_id`。
- Worker 步骤：
  1. 加载 job，下载 `source_object_key` 到临时目录。
  2. `registry.get_strategy(file_ext)`。
  3. 若 `pdf` 且 `strategy.needs_ocr(local_path)` → `ocr_bridge.run`：创建 `ocr_file`、轮询至 `SUCCESS` 或超时 → 写 `ocr_file_id`、`OCR_RUNNING`。
  4. `segments = strategy.extract(...)` → 批量插入 `doc_translate_segment`（`PENDING`），更新 `segment_total`。
  5. 并发池（建议 max 5）逐段 `translate_llm.translate_segment`；成功写 `translated_text` + `DONE`，递增 `segment_done`；失败写 `FAILED` 并中止任务为 `FAILED`。
  6. `strategy.assemble(segments, source_local, out_local)` → 上传 `result_object_key` → `SUCCESS`。
  7. 清理临时文件；异常路径写 `error_code` / `error_message`。

### 4.3 OCR 桥接（`ocr_bridge.py`）

- 复用 `file_ocr` 创建任务 API / service（与前端 OCR 任务列表相同入库路径）。
- `translate_job` 使用独立 `module_prefix`（如 `translate/source/`）上传源文件；OCR 使用既有 `ocr_file` 流程。
- 轮询间隔与超时（建议：2s 间隔，最大 30 分钟）写入 `translate` 常量或 `config.py`。
- OCR 失败：`error_code=translate.ocr_failed`。

### 4.4 段落翻译 Prompt（`translate_llm.py`）

- System：专业翻译，仅输出译文，不解释；源语言 `{source_lang}`，目标语言 `{target_lang}`。
- User：单段原文。
- 使用 `chat_service.complete`（非流式），温度建议 0.2–0.3。
- 模型凭证从 `sys_models` 解析，与 agent 运行一致；**禁止**将 api_key 写入 segment 表。

---

## 5. 格式策略（按后缀）

### 5.1 抽象接口

```python
class DocTranslateFormatStrategy(ABC):
    extensions: ClassVar[frozenset[str]]

    def needs_ocr(self, local_path: Path) -> bool: ...  # 默认 False；pdf 覆盖

    def extract(self, local_path: Path, *, ocr_file_id: UUID | None) -> list[SegmentDraft]: ...

    def assemble(
        self,
        segments: list[SegmentRecord],
        source_path: Path,
        out_path: Path,
    ) -> None: ...
```

`SegmentDraft`：`seq`, `source_text`, `anchor_json`。  
注册表：`get_doc_translate_strategy(ext: str) -> DocTranslateFormatStrategy`，未知后缀 `KeyError` → API `422`。

### 5.2 各格式要点（全格式一期交付）

| 后缀 | 抽取 | 写回 | OCR |
|------|------|------|-----|
| `txt` | 连续空行分段 | 按段还原，段间双换行 | — |
| `md` | 同 txt，保留 fenced code 块为单段（不拆行内） | 同序写回 | — |
| `csv` | 非表头字段级抽取，`anchor_json` 含行列位置 | 按字段位置写回，保留行列结构 | — |
| `docx` | 段落 + 表格单元格为段，`anchor_json` 含 paragraph/table 索引 | python-docx 保留 run 样式 | — |
| `doc` | 经 LibreOffice 转为 DOCX 后复用 Word 策略 | 写回 DOCX 中间结果后按 legacy Word 流程输出 | — |
| `pdf` | 有文字层：按块/行聚合；无文字层：`needs_ocr=True` | PyMuPDF 按 anchor 替换或叠加（尽力版式） | 扫描件自动 OCR |
| `xls` | legacy xls cell 策略按工作簿/单元格抽取 | 按单元格锚点写回，保留行列结构 | — |
| `xlsx` | 非表头单元格级抽取，`anchor_json` 含 sheet/row/col | 按 sheet/row/col 写回单元格 | — |

### 5.3 段落过长

- 单段超过模型上下文安全阈值（如 6k 字符）时，策略层按句切分为多条 `seq` 连续记录，组装时合并；或在 `extract` 阶段禁止超长并拆句。

---

## 6. HTTP API

前缀：`/workspaces/{workspace_id}/translate`（需 `require_workspace_member`）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/jobs` | `multipart/form-data`：`file`, `source_lang`, `target_lang`, `model_id`；校验后缀/大小；S3 上传；插入 job `PENDING`；`enqueue` Celery |
| `GET` | `/jobs` | 列表：`page` / `page_size` offset 分页 + 文件名 / 状态 / 创建时间筛选 |
| `GET` | `/jobs/{job_id}` | 详情 + 状态 + 进度 |
| `GET` | `/jobs/{job_id}/segments` | 对照列表，按 `seq` 排序；单次最多 **5000** 段 |
| `GET` | `/jobs/{job_id}/download` | 译文下载（`SUCCESS` 且 `result_object_key` 存在） |
| `DELETE` | `/jobs/{job_id}` | 业务删除 segments + S3 源/结果 + job |

### 6.1 校验

- 后缀白名单：`doc`, `docx`, `pdf`, `txt`, `md`, `csv`, `xls`, `xlsx`。
- 单文件大小上限：**20MB**（常量，可配置）。
- `model_id`：存在、属当前 `workspace_id`、`model_type` 为 translate 字典项、enabled、endpoint + api_key 有效。

### 6.2 列表分页与筛选（2026-05-21）

| 参数 | 说明 |
|------|------|
| `page` / `page_size` | offset 分页，默认 `page_size=10` |
| `file_name` | 可选，`ILIKE` 模糊 |
| `status` | 可选，精确匹配 |
| `create_at_start` / `create_at_end` | 可选 |

响应：`{ items, total }`。keyset `cursor` 已不再用于列表 API。

---

## 7. 前端 UI（2026-05-21 表格 + Modal）

### 7.1 布局（参考 `FileOcrTaskPage`）

- 单栏：`Card` + inline 筛选 Form + `Table`（`scroll.y` 自适应）。
- `AppLayout` 对 `/app/translate` 使用标准列表页 padding（20px）。

### 7.2 任务表格

- `useQuery` + `page` / `page_size` / 筛选参数拉取列表。
- 列：文件名、语言、状态、进度、创建时间、操作（查看 / 下载 / 删除）。
- 行点击打开详情全屏 Modal。

### 7.3 上传 Modal

- 「新建翻译」打开 Modal：`Upload.Dragger`、源/目标语言、translate 模型；`POST /jobs` 不变。
- 成功后关闭 Modal、刷新表格、自动打开详情 Modal。

### 7.4 详情全屏 Modal

- 顶栏：状态 Tag、Progress、`segment_done/total`、下载（`SUCCESS`）。
- 主体：双列对照；非终态 **3s 轮询**；`FAILED` 显示 `error_message`。

### 7.5 i18n 键（示例）

- `translate.filter.*`, `translate.table.*`, `translate.uploadModal.title`, `translate.detailModal.title`, `translate.newJob`, `translate.status.*`

---

## 8. 删除与一致性

`delete_doc_translate_job(job_id)`（同一事务）：

1. `DELETE FROM doc_translate_segment WHERE job_id = ?`
2. S3 删除 `source_object_key`、`result_object_key`（若存在）
3. `DELETE FROM doc_translate_job WHERE id = ?`
4. **不删除** `ocr_file` 行

---

## 9. 错误码（示例）

| code | 场景 |
|------|------|
| `translate.unsupported_ext` | 后缀不在白名单 |
| `translate.file_too_large` | 超过大小限制 |
| `translate.model_invalid` | 模型非 translate 或未配置 |
| `translate.ocr_failed` | 扫描 PDF OCR 失败或超时 |
| `translate.extract_failed` | 抽取失败 |
| `translate.translate_failed` | 段落翻译失败 |
| `translate.assemble_failed` | 写回失败 |
| `translate.job_not_found` | 404 |

---

## 10. 测试计划

| 层级 | 内容 |
|------|------|
| 策略单测 | txt/md/csv roundtrip；docx/xlsx 小样；pdf 文本层小样 |
| OCR 桥接 | mock `ocr_file` 状态流转 |
| API | 创建 job、列表 offset 分页 / 筛选 / total、segments、删除清理 |
| Worker | mock LLM，端到端 job → SUCCESS |
| 前端 | 列表/轮询/对照列布局快照（可选） |

---

## 11. 配置与环境变量（实现时）

若新增 OCR 等待超时、段落并发数、文件大小上限，须同步：

- `backend/app/config.py`
- `backend/.env.example`
- `backend/.env.dev`

---

## 12. 已确认决策记录

| 项 | 决策 |
|----|------|
| 架构 | 统一段落中间模型 + 单 Celery 流水线 |
| 表名 | `doc_translate_job`、`doc_translate_segment` |
| 历史 | 一条 job = 表格一行（2026-05-21 起无侧栏） |
| 语言 | 每任务上传区选择源 + 目标语言 |
| 模型 | `model_type = translate` |
| PDF 扫描件 | 自动 OCR 后翻译，版式尽力保留 |
| 交付 | 左右段落对照 + 下载 |
| 进度 | 首期 HTTP 轮询（约 3s） |
| 范围 | `doc`, `docx`, `pdf`, `txt`, `md`, `csv`, `xls`, `xlsx` 当前实现支持 |
| 数据库 | 无外键、无级联删除 |

---

## 13. 后续迭代（非本期）

- SSE 任务进度。
- 失败段单独重试 / `PARTIAL_SUCCESS`。
- 多文件打包翻译、术语表、翻译记忆库。

---

## 实现对照（以代码为准，2026-05-23）

| 条目 | 当前代码位置 | 备注 |
|------|--------------|------|
| 结构化写回 | `backend/app/layout/writers/` | CSV / XLS / XLSX / DOC / DOCX / PDF 已收敛到 writer 层或 legacy 转换策略 |
| Markdown skip | `backend/app/translate/service/strategies/md_strategy.py` | fenced code 使用 `skip_translate=true` |
| doc/xls 支持 | `backend/app/translate/service/strategies/word_strategy.py`, `backend/app/translate/service/strategies/xls_strategy.py` | 作为当前实现支持范围记录 |
