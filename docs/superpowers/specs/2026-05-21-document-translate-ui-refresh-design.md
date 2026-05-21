# 文档翻译页 UI 重构（表格 + 筛选 + 弹窗）设计说明

**日期**：2026-05-21  
**状态**：已批准（待实现）  
**前置**：`docs/superpowers/specs/2026-05-20-document-translate-design.md`（流水线、策略、对照能力不变）  
**范围**：`minerva-ui/src/features/translate/` 主页面交互重构；`GET /workspaces/{id}/translate/jobs` 列表 API 改为 offset 分页 + 筛选；上传与详情改为 Modal；**不**改动 `POST /jobs`、Celery、格式策略、段落翻译、删除与 S3 逻辑。

---

## 1. 目标与成功标准

### 1.1 目标

- 翻译任务主界面由「左侧历史 + 右侧上传/对照」改为 **单栏表格列表**，顶部 **inline 搜索条件**（对齐 OCR 任务页习惯）。
- **新建翻译**：原居中上传区改为 **Modal 弹窗**，表单字段与 `createTranslateJob` 调用不变。
- **任务详情**：**全屏 Modal**，内含原左右段落对照区（内滚动），保留 3s 轮询、进度、下载、失败提示。
- 列表 API 支持 **文件名模糊、状态、创建时间范围** 服务端筛选 + `total` 分页。

### 1.2 成功标准

- 用户可通过筛选 + 分页浏览全部翻译任务；行点击或「查看」打开全屏详情 Modal，对照与下载行为与改版前一致。
- 上传成功后列表刷新，并 **自动打开** 该任务的详情全屏 Modal。
- 删除仍使用 `Popconfirm`；仅 `SUCCESS` 行显示下载。
- 后端翻译流水线、上传校验、segments/download/delete 接口无行为回归。

### 1.3 非目标

- SSE 进度、失败段重试、侧栏 keyset「加载更多」交互。
- 列表筛选增加源/目标语言（本期不做）。
- 浏览器内嵌 PDF/Word 预览。

---

## 2. 已确认决策

| 项 | 决策 |
|----|------|
| 列表布局 | 单栏 Table + 顶部筛选（移除左侧历史侧栏） |
| 筛选字段 | 文件名（模糊）、状态、创建时间范围（与 OCR 任务页 A+B+C 一致） |
| 新建入口 | Modal，内容与现上传 Form 一致 |
| 详情展示 | 全屏 Modal，对照区内滚动 |
| 上传成功后 | 关闭上传 Modal → 刷新表格 → 自动打开详情 Modal |
| 列表 API | 方案 A：扩展现有 `GET /jobs`，替换 cursor 分页（唯一消费者为翻译页） |
| 后端流水线 | 不变 |

---

## 3. 后端变更

### 3.1 `GET /workspaces/{workspace_id}/translate/jobs`

**查询参数**（对齐 `file_ocr` 的 `list_ocr_files`）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int，默认 1 | ≥1 |
| `page_size` | int，默认 10 | 1–100，与 `app.pagination.DEFAULT_PAGE_SIZE` 一致 |
| `file_name` | string，可选 | 非空时 `file_name ILIKE %trim%` |
| `status` | string，可选 | 非空时精确匹配 `doc_translate_job.status` |
| `create_at_start` | datetime，可选 | `create_at >=` |
| `create_at_end` | datetime，可选 | `create_at <=` |

**响应**（替换原结构）：

```json
{
  "items": [ /* DocTranslateJobListItemOut */ ],
  "total": 0
}
```

- 排序：`COALESCE(update_at, create_at) DESC, id DESC`（与现侧栏一致）。
- **移除** 对外暴露的 `cursor` / `next_cursor`（`encode_doc_translate_job_cursor` 可保留于仓库供日后复用，列表路由不再使用）。

### 3.2 Repository

- 新增 `list_doc_translate_jobs_filtered(session, workspace_id, *, page, page_size, file_name, status, create_at_start, create_at_end) -> tuple[list[DocTranslateJob], int]`。
- 实现：`WHERE workspace_id = ?` + 动态条件 → `count(*)` → `offset/limit`。

### 3.3 Schemas

- `DocTranslateJobListOut`：`items` + `total`（替换 `jobs` + `next_cursor`）。
- `DocTranslateJobListItemOut` 字段不变。

### 3.4 不变接口

- `POST /jobs`（multipart）、`GET /jobs/{id}`、`GET /jobs/{id}/segments`、`GET /jobs/{id}/download`、`DELETE /jobs/{id}` — 无变更。

---

## 4. 前端变更

### 4.1 页面结构（`TranslatePage.tsx`）

参考 `FileOcrTaskPage`：

```text
Card
  Form (inline) — 筛选 + 搜索/重置 + 「新建翻译」
  Table — 任务列表，分页，纵向 scroll.y 自适应
Upload Modal — Dragger + 语言 + 模型 + 提交
Detail Modal (fullscreen) — 工具栏 + 双列对照（body 内滚动）
```

- 移除 `translate-page__sider`、`useInfiniteQuery`、`handleShowUpload` 等侧栏逻辑。
- `AppLayout`：`/app/translate` 主区 padding 改为与普通管理列表页一致（不再复用 agents 双栏零 padding）；实现时对照 OCR 任务页路由配置。

### 4.2 筛选栏

| 表单项 | 控件 | 行为 |
|--------|------|------|
| 文件名 | `Input` + `allowClear` | 点「搜索」写入 applied 状态并 `page=1` |
| 状态 | `Select` + `allowClear` | 选项为全部 `doc_translate_job.status` 枚举 |
| 创建时间 | `DatePicker.RangePicker` + `allowClear` | 映射为 `create_at_start` / `create_at_end`（ISO 或 API 约定格式，与 OCR 一致） |
| 操作 | 搜索 / 重置 / 新建翻译 | 重置清空 applied 并刷新 |

- 使用 `useQuery` + `page` / `pageSize` 拉取列表；默认 `pageSize = DEFAULT_PAGE_SIZE`（10）。

### 4.3 表格列

| 列 | 数据 | 备注 |
|----|------|------|
| 文件名 | `file_name` 或 `title` | `ellipsis` |
| 语言 | `source_lang` → `target_lang` | i18n 语言标签 |
| 状态 | `status` | `Tag` + `translate.status.*` |
| 进度 | 非终态 | `Progress` 或 `segment_done/segment_total` |
| 创建时间 | `create_at` | 与 `formatTranslateJobDate` 一致 |
| 操作 | 查看 / 删除 / 下载 | 下载仅 `SUCCESS`；删除 `Popconfirm` |

- `rowKey="id"`；行点击打开详情 Modal（与「查看」相同）。
- 分页：`showSizeChanger`，`pageSizeOptions: [10, 20, 50, 100]`。

### 4.4 上传 Modal

- 触发：筛选栏「新建翻译」（`type="dashed"`）。
- 内容：自现主区迁移 — `Upload.Dragger`（`ACCEPT` 不变）、源/目标语言 `Select`（`allowClear={false}`）、模型 `Select`、无 translate 模型时的 `Alert` + 设置链接。
- 提交：`createTranslateJob`；`loading` 态；成功 → 关闭 Modal、清空文件、`invalidateQueries` 列表、设置 `detailJobId` 打开详情 Modal。
- `destroyOnHidden`：关闭时重置表单本地状态。

### 4.5 详情全屏 Modal

- `open={detailJobId != null}`；标题区：文件名、`Tag` 状态、非终态 `Progress`、`segment_done/total`、`SUCCESS` 时下载按钮。
- Body：`translate-page__compare-grid` 双列；`overflow: auto` + `minerva-scrollbar-styled`。
- 查询：`getTranslateJob` + `listTranslateJobSegments`；非终态 `refetchInterval: 3000`（与现逻辑相同）。
- `FAILED`：`Alert` 展示 `error_message`。
- Footer：`null` 或仅「关闭」；关闭后 `detailJobId = null`，表格不强制高亮行。

### 4.6 API 客户端（`api/translate.ts`）

- `listTranslateJobs(workspaceId, { page, page_size, file_name?, status?, create_at_start?, create_at_end? })`。
- 类型：`DocTranslateJobListOut = { items, total }`。

### 4.7 样式（`TranslatePage.css`）

- 删除侧栏相关规则；保留/调整 `__compare-grid`、`__segment-row`、`__toolbar` 供详情 Modal 使用。
- 新增表格页容器类（可对齐 `minerva-file-ocr-tasks-page` 的 filter/table-wrap 模式）。

### 4.8 i18n

新增示例键：

- `translate.filter.fileName`, `translate.filter.status`, `translate.filter.createRange`
- `translate.table.view`, `translate.table.fileName`, `translate.table.lang`, …
- `translate.uploadModal.title`, `translate.detailModal.title`
- `translate.newJob`（新建按钮）

可废弃或不再使用的键：`translate.history`, `translate.loadMore`, `translate.newTranslate`（实现时清理未引用项）。

---

## 5. 对原设计文档的修订说明

实现完成后须回填 `2026-05-20-document-translate-design.md` **§7 前端 UI**：

- §7.1–7.4 由「Agents 双栏 + 侧栏 keyset」改为本文 **§4** 描述。
- §6.2 列表游标改为 offset + 筛选（或在 §6 增加分页列表说明）。
- §12 决策表增加「列表 UI：表格 + Modal」一行。

---

## 6. 测试计划

| 层级 | 内容 |
|------|------|
| Repository/API | 分页 total；`file_name` 模糊；`status`；时间范围；空筛选 |
| 前端 | 筛选重置；上传成功自动开详情；Modal 内轮询至 SUCCESS/FAILED；删除刷新列表 |
| 回归 | `POST /jobs` 六种后缀；download；segments 上限 |

---

## 7. 实现顺序建议

1. 后端：`list_doc_translate_jobs_filtered` + router/schema 响应变更 + API 测试。
2. 前端 API 类型与 `listTranslateJobs` 参数更新。
3. `TranslatePage` 表格 + 筛选 + 双 Modal。
4. CSS / i18n / `AppLayout` 路由 padding。
5. 回填 `2026-05-20-document-translate-design.md` §7、§6.2。
