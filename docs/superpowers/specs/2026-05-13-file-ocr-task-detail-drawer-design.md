# 文件 OCR：任务列表「查看详情」抽屉（按 `ocr_type` 策略取数 + Markdown 渲染）

**日期**：2026-05-13  
**状态**：已实现（2026-05-18 按代码回填）  
**依据**：头脑风暴结论——采用 **方案一**：后端只做「鉴权 + 校验状态 + 按 `ocr_type` 策略读结果表 + `page_index` 排序 + 规范化 DTO」；**占位符与图片 URL/data URI 的替换在前端完成**；列表入口 **仅 `status === 'SUCCESS'`** 可点；抽屉 **宽度约 80% 视口**；`markdown_images` 为 **JSON 对象**（`dict[str, str]`），与现有 Paddle 落库方式一致（`backend/app/file_ocr/service/strategies/paddle.py`）。

---

## 1. 背景与目标

- 任务列表页（`文件OCR > 任务列表`）已有「查看详情」入口，当前为占位行为。
- 目标：用户点击后，以 **Drawer** 展示该任务在 **`ocr_file_paddleocr`** 或 **`ocr_file_mineru`** 中的 **按页 OCR 结果**，以 **Markdown** 渲染；取数路径与 **`ocr_file.ocr_type`** 对齐，采用 **策略模式（只读）**，与写路径策略分离但 **注册键一致**（`PADDLE_OCR` / `MINERU`）。

---

## 2. 范围与边界

### 2.1 本次范围

- 后端新增 **只读** HTTP 接口：按 `workspace_id` + `ocr_file_id` 返回有序页面列表（见第 5 节）。
- 后端新增 **`ocr_type` → 结果表** 的 **只读策略**（或等价注册表 + 函数），查询 **`ORDER BY page_index ASC NULLS LAST`**。
- 前端：操作列「查看详情」在 **非 `SUCCESS`** 时 **禁用**（可加 Tooltip 说明）；`SUCCESS` 时打开 Drawer（**宽度 80%**，与 Ant Design `Drawer` 的 `width` 语义一致，如 `80%`）。
- 前端：请求接口 → 对每页解析 `images` → 按约定 **替换 `markdown_text` 中的占位符** → 使用 **`react-markdown` + `remarkGfm`** 渲染（与 `RulesManagementPage` 模式对齐）。
- 多页时在 UI 层为每页增加 **可读页标题**（见 6.3），再拼接该页 MD 正文。

### 2.2 非本次范围

- **图片代理 / SSRF 治理**：当前假定结果来自已信任 OCR 管道；外链图片不在本期做后端代理。
- **MinerU 解析流水线**：若策略尚未向 `ocr_file_mineru` 写入数据，详情接口仍应对 `MINERU` 类型返回 **200 + 空 `pages`**（与「表空」一致），不视为错误。
- **下载结果、重新 OCR** 等其它操作列能力：不在本文档扩展，沿用既有占位或独立 Story。

---

## 3. 数据与字段约定（冻结）

### 3.1 表与类型映射

| `ocr_file.ocr_type` | 只读查询表 |
|---------------------|------------|
| `PADDLE_OCR` | `ocr_file_paddleocr` |
| `MINERU` | `ocr_file_mineru` |

### 3.2 行语义

- 每行对应文档的一页（或引擎给出的一页切片），以 **`page_index`** 排序；与写入侧一致时 **`page_index` 为从 0 开始的整数**（见 Paddle 策略 `enumerate`）；若个别行为 `NULL`，排序规则 **`NULLS LAST`**。
- **`markdown_text`**：该页 Markdown 字符串，可为 `NULL`。
- **`markdown_images`**：库中为 **TEXT**；业务语义为 **一个 JSON 对象**：键为出现在 `markdown_text` 中的 **占位符字符串**，值为 **`http(s)` URL 或 `data:` URI**（与 Paddle `markdown.images` 一致）。存库时为 `json.dumps(obj, ensure_ascii=False)`；**空对象或无图** 时字段可为 `NULL` 或省略解析结果中的 `images`。

### 3.3 MinerU 写入约定（面向二期）

- 当 MinerU 策略落地写 `ocr_file_mineru` 时，**必须**采用与 3.2 相同的 JSON 语义，以便 **同一套前端替换与详情 DTO** 无需分叉。

---

## 4. 行为规则（冻结）

### 4.1 列表按钮

- **`status !== 'SUCCESS'`**：「查看详情」**禁用**。
- **`status === 'SUCCESS'`**：可点击，打开抽屉并拉取详情。

### 4.2 接口与任务状态

- 若客户端在 **非 `SUCCESS`** 时仍调用详情接口（例如竞态）：服务端返回 **`409 Conflict`**，响应体使用项目统一的 **`AppError`** 形状（`code` + `message`）；**不使用 404**，以免与「任务不存在」混淆。
- 若 **`ocr_file_id` 不属于该 `workspace_id` 或不存在**：**`404 Not Found`**。

### 4.3 未知或不支持的 `ocr_type`

- 主表存在但 `ocr_type` 无对应只读策略：返回 **`422 Unprocessable Entity`**（或项目约定的「业务不支持」状态码，实现计划在接入全局异常映射时二选一并写死）。

---

## 5. API 设计（建议）

### 5.1 路由与方法

- **`GET /workspaces/{workspace_id}/ocr-files/{ocr_file_id}/markdown-pages`**
- 鉴权：`get_current_user` + `require_workspace_member`（与现有 `file_router` 一致）。

### 5.2 成功响应 `200`

```json
{
  "file_id": "<uuid>",
  "ocr_type": "PADDLE_OCR",
  "pages": [
    {
      "page_index": 0,
      "markdown_text": "# ...",
      "images": { "placeholder-a": "data:image/png;base64,..." }
    }
  ]
}
```

- **`images`**：服务端将 `markdown_images` 解析为对象后的结果；若字段为 `NULL` 或 JSON 非法，则该页 **`images` 为 `null`**（不在此页失败整请求）。
- **`pages`**：已按 **`page_index ASC NULLS LAST`** 排序。

### 5.3 空结果

- **`SUCCESS`** 且策略对应表中 **零行**：**`200`**，`pages: []`；抽屉展示「暂无 OCR 内容」类文案。

---

## 6. 前端交互与渲染

### 6.1 Drawer

- **`width="80%"`**（或与设计稿一致的 `80vw`，实现计划中选一并全仓统一）。
- 标题：建议 **`file_name`（自列表行缓存）** + OCR 类型字典展示（`DictText` 同源字典码）。
- 关闭后 **取消进行中的请求**（`AbortController`）以避免竞态写状态。

### 6.2 占位符替换算法（冻结）

对单页字符串 `text` 与对象 `images`（非 `null`）：

1. 若 `images` 无键，直接使用 `text`。
2. 否则将 **`images` 的键按长度降序排序**，依次执行 **全局字符串替换**：`text = text.split(key).join(images[key])`（或等价实现），以避免较短键误伤较长键的前缀。
3. 将结果交给 `ReactMarkdown`。

若后续确认引擎 **固定** 使用某种包裹格式（例如仅 `![](key)`），可在实现阶段收紧替换规则并补充测试，**本规格以 6.2 的通用替换为默认**。

### 6.3 多页版式

- 对每个 `page` 渲染块：**二级标题** **`第 {page_index + 1} 页`**（当 `page_index` 为数字时）；若 `page_index` 为 `null`，退化为按数组顺序 **`第 {i+1} 页`**（`i` 为 `pages` 中顺序下标）。

### 6.4 加载与错误

- 加载中：Skeleton 或 `Spin`。
- **409**：提示「仅成功任务可查看详情」。
- **422**：提示「当前 OCR 类型暂不支持详情」。
- **网络错误**：统一错误提示组件。

---

## 7. 后端组件划分（建议）

### 7.1 只读策略接口

- 定义协议，例如 **`FileOcrResultReadStrategy`**：`ocr_type: ClassVar[str]`，`async def load_pages(session, workspace_id, file_id) -> list[NormalizedPage]`。
- **`PADDLE_OCR`** 实现：查询 `OcrFilePaddleocr`。
- **`MINERU`** 实现：查询 `OcrFileMineru`。
- **注册表**：`ocr_type` → 实现类；路由层先 **`select OcrFile` 校验 workspace + 存在性**，再 **`status == SUCCESS`**，否则 **409**；再按 `ocr_type` 取策略。

### 7.2 与写策略的关系

- **写策略**（`app/file_ocr/service/strategies/*.py`）与 **读策略** 可同目录或子包 `.../strategies/read/`；**禁止**在 `router` 内写 `if ocr_type == ...: select(...)` 长分支，**必须通过注册表** 解析。

---

## 8. 测试要求

### 8.1 后端

- **`SUCCESS` + 多页 Paddle 数据**：返回顺序与 `page_index` 一致；`images` JSON 合法时正确反序列化。
- **`markdown_images` 非法 JSON**：该页 `images: null`，整体 **200**。
- **`PROCESS` / `INIT` / `FAILED`**：**409**。
- **错误 `workspace` 或 `id`**：**404**。
- **未知 `ocr_type`**：**422**（若主表可被历史数据写入异常值，则覆盖此用例）。

### 8.2 前端

- **禁用态**：非 `SUCCESS` 不可点。
- **替换逻辑**：至少一单测或 Story 级用例覆盖「长短 key」「无 images」。

---

## 9. 与既有规格的关系

- 任务列表总览与操作列规划见 `docs/superpowers/specs/2026-04-30-file-ocr-task-list-design.md`；本文档将其中 **「查看详情」** 从占位落实为可交付行为。
- Celery 扫描与写表见 `docs/superpowers/specs/2026-05-13-file-ocr-init-scanner-design.md`；本文档只依赖 **结果表已有数据** 与主表 **`SUCCESS`** 状态。

---

## 10. 实现计划入口

用户审阅本文档并确认无修改后，使用 **`writing-plans`** 技能生成实现计划。**已完成**。

---

## 11. 实现对照（以代码为准，2026-05-18）

| 项 | 代码 |
|----|------|
| API | `GET .../ocr-files/{id}/markdown-pages` |
| 非 SUCCESS | 409 |
| 读策略 | `file_ocr/service/result_read/`（PADDLE/MINERU） |
| UI | `FileOcrTaskPage.tsx` Drawer `width="80%"` |
| 占位符 | `applyOcrMarkdownImagePlaceholders.ts` |
| 取消请求 | `AbortController` |
