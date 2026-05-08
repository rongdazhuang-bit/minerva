# PaddleOCR-VL 服务化 API 客户端（app/ocr/paddleocr）设计说明

**日期**：2026-05-08  
**状态**：已澄清待评审  
**依据**：[PaddleOCR-VL 使用教程 — 4.3 客户端调用方式](https://www.paddleocr.ai/main/version3.x/pipeline_usage/PaddleOCR-VL.html#43-%E5%AE%A2%E6%88%B7%E7%AB%AF%E8%B0%83%E7%94%A8%E6%96%B9%E5%BC%8F)（`infer` / `restructurePages` 的请求与响应字段）。

---

## 1. 目标与边界

- **目标**：在 `backend/app/ocr/paddleocr/` 提供与 **PaddleX 服务化部署**一致的 **HTTP JSON 客户端**，以及 **Pydantic 请求/响应模型**，便于业务或其它模块在持有完整 URL 与鉴权信息的前提下发起调用。
- **边界（已澄清）**：
  1. **`SysOcrTool.url` 存完整 URL**（含 path），例如 `http://host:8080/layout-parsing`。客户端 **不对 path 做拼接或改写**，仅对传入的 URL 发起 `POST`。
  2. **本模块只做 API 集成**：**所有业务参数（含请求体字段）均由调用方构造并传入**；不在此模块内读取数据库、不读取 `SysOcrTool`、不合并 `ocr_config`（调用方自行从配置行组装 `LayoutParsingRequest` 等）。
  3. **定义显式的请求参数类与响应参数类**（Pydantic v2），与官方文档中的 **JSON 字段名（camelCase）** 一致（通过 `Field(validation_alias=..., serialization_alias=...)` 或等价方式，保证 `model_dump(by_alias=True)` 可直接作为请求体）。

**成功标准**：调用方传入完整 URL + 已填充的请求模型后，客户端能发出符合文档的 JSON、解析统一信封响应，并在 `errorCode != 0` 或 HTTP 非 2xx 时抛出可区分的错误类型（含 `logId` / `errorMsg` 等）。

---

## 2. 模块结构与依赖

| 内容 | 说明 |
|------|------|
| 位置 | `backend/app/ocr/paddleocr/` |
| 允许依赖 | 标准库、`httpx`、`pydantic` |
| 禁止依赖 | `sqlalchemy`、`SysOcrTool`、`file_ocr`、`sys.tool` 路由或服务层 |

可选：薄封装 `async def post_layout_parsing(url: str, body: LayoutParsingRequest, *, client: httpx.AsyncClient | None = None, headers: Mapping[str, str] | None = None) -> LayoutParsingResponse`；鉴权头由调用方传入（与 `auth_type` / 密钥到 Header 的映射留在业务或 `sys.tool` 侧）。

---

## 3. 请求模型（`infer` → `POST` 调用方提供的完整 URL）

以下与文档 **4.3** 中 `POST /layout-parsing` 请求体对齐。实现时使用 **一个** Pydantic 模型（例如 `LayoutParsingRequest`），字段必填性以文档为准：**仅 `file` 为必填**（由调用方赋值），其余均为可选。

| JSON 键（camelCase） | 类型（文档） | 说明 |
|----------------------|-------------|------|
| `file` | string | 必填。URL 或文件内容 Base64。 |
| `fileType` | integer \| null | 0=PDF，1=图像；可省略由服务推断。 |
| `useDocOrientationClassify` | boolean \| null | 可选。 |
| `useDocUnwarping` | boolean \| null | 可选。 |
| `useLayoutDetection` | boolean \| null | 可选。 |
| `useChartRecognition` | boolean \| null | 可选。 |
| `useSealRecognition` | boolean \| null | 可选。 |
| `useOcrForImageBlock` | boolean \| null | 可选。 |
| `layoutThreshold` | number \| object \| null | 可选。 |
| `layoutNms` | boolean \| null | 可选。 |
| `layoutUnclipRatio` | number \| array \| object \| null | 可选。 |
| `layoutMergeBboxesMode` | string \| object \| null | 可选。 |
| `layoutShapeMode` | string | 可选。 |
| `promptLabel` | string \| null | 可选。 |
| `formatBlockContent` | boolean \| null | 可选。 |
| `repetitionPenalty` | number \| null | 可选。 |
| `temperature` | number \| null | 可选。 |
| `topP` | number \| null | 可选。 |
| `minPixels` | number \| null | 可选。 |
| `maxPixels` | number \| null | 可选。 |
| `maxNewTokens` | number \| null | 可选。 |
| `mergeLayoutBlocks` | boolean \| null | 可选。 |
| `markdownIgnoreLabels` | array \| null | 可选。 |
| `vlmExtraArgs` | object \| null | 可选。 |
| `prettifyMarkdown` | boolean | 可选；文档默认 `true`。 |
| `showFormulaNumber` | boolean | 可选；文档默认 `false`。 |
| `restructurePages` | boolean | 可选；文档默认 `false`。 |
| `mergeTables` | boolean | 可选；仅当 `restructurePages` 为 true 时语义生效。 |
| `relevelTitles` | boolean | 可选；同上。 |
| `outputFormats` | array \| null | 可选；如 `["docx"]`。 |
| `visualize` | boolean \| null | 可选。 |

**多形态字段建模**：`layoutThreshold`、`layoutUnclipRatio`、`layoutMergeBboxesMode` 等允许 number / string / list / dict 的，在 Pydantic 中使用 `Union[...]` 或 `JsonValue`（若项目已有统一类型）以减少强制转换；以 **与服务 JSON 兼容** 为第一约束。

**序列化策略**：默认对请求使用 `model_dump(mode="json", by_alias=True, exclude_none=True)`（若业务需显式传 `null` 覆盖服务端行为，可再提供 `exclude_none=False` 的选项或在 spec 实现阶段约定）。

---

## 4. 响应模型（统一信封 + `infer` 结果）

### 4.1 信封（成功 / 失败通用）

与文档一致：

| JSON 键 | 类型 | 含义 |
|---------|------|------|
| `logId` | string | 请求 UUID。 |
| `errorCode` | integer | 成功为 `0`；失败时与状态码含义一致（见文档）。 |
| `errorMsg` | string | 说明。 |
| `result` | object \| null | 成功时承载业务结果；失败时可为空或省略，以实际服务为准。 |

实现建议：**单一模型** `PaddleOcrVlApiResponse[T]` 或 **非泛型** `LayoutParsingApiResponse`，内含 `result: LayoutParsingResult | None`。

### 4.2 `result`（`infer` 成功时）

| JSON 键 | 类型 | 模型建议 |
|---------|------|----------|
| `layoutParsingResults` | array | `list[LayoutParsingPageResult]` |
| `dataInfo` | object | `dict[str, Any]` 或独立 `DataInfo`（若后续字段稳定再收紧） |

### 4.3 `layoutParsingResults[]` 每项

| JSON 键 | 类型 | 模型建议 |
|---------|------|----------|
| `prunedResult` | object | **`dict[str, Any]`**（结构随产线版本变化，首版不做深 schema） |
| `markdown` | object | `MarkdownResult`（`text: str`, `images: dict[str, str]`，值为 Base64） |
| `outputImages` | object \| null | `dict[str, str] \| None` |
| `inputImage` | string \| null | 可选。 |
| `exports` | object \| null | `dict[str, Any] \| None`（如 `docx.content` Base64） |

---

## 5. `restructurePages`（可选，同一设计原则）

- 调用方传入 **完整 URL**（例如 `http://host:8080/restructure-pages`，仍来自配置或常量，由业务决定）。
- **请求模型** `RestructurePagesRequest`：字段与文档一致——`pages`（必填，元素含 `prunedResult`、`markdownImages`）、`mergeTables`、`relevelTitles`、`concatenatePages`、`prettifyMarkdown`、`showFormulaNumber`、`outputFormats`。
- **响应**：同一信封结构；`result` 内含 `layoutParsingResults`（与文档 4.3 描述一致），可复用 `LayoutParsingPageResult` 的子集或单独 `RestructurePagesResult` 避免循环引用，实现阶段以类型清晰为准。

---

## 6. 错误与 HTTP 语义

- **HTTP 层**：非成功状态码 → 抛出 `PaddleOcrVlTransportError`（或等价名），附带 `response.text` 截断。
- **业务错误**：HTTP 200 但 `errorCode != 0` → 抛出 `PaddleOcrVlApiError`，附带 `logId`、`errorCode`、`errorMsg`、原始 body。
- **解析错误**：JSON 无法解析为响应模型 → `ValidationError` 包装或专用异常，便于调用方记录。

不在本模块内写 `OcrFile.remark` 等业务副作用。

---

## 7. 与 `SysOcrTool` 的协作方式（仅说明，非本模块职责）

- 业务加载 `SysOcrTool` 后：**`url` 原样作为 POST 目标**；将 `ocr_config` 反序列化后 **映射/校验** 为 `LayoutParsingRequest`（可部分字段 + `model_validate`）；**`file` 由业务**从存储读取后 Base64 或改为可访问 URL 填入请求。
- 若现有 `url` 列长度（当前 128）不足以容纳完整 URL，属 **数据模型迁移**，不在本客户端 spec 内强制，实现前由业务确认是否需 Alembic 扩容。

---

## 8. 测试建议

- 使用 `httpx.MockTransport` 构造固定 JSON 响应，断言：请求 URL 未被改写、body 别名与文档一致、错误码分支抛对异常。
- 无需启动真实 Paddle 服务即可单测。

---

## 9. 自检（spec 质量）

- **无 TBD**：URL 形态、参数来源、模型分层已按澄清写死。  
- **一致性**：请求/响应字段名与官方 4.3 表一致；`prunedResult` 等易变结构用 `dict` 避免虚假精度。  
- **范围**：单库内 HTTP 客户端 + 模型；不含 DB、不含任务状态机。  
- **歧义**：「完整 URL」已明确包含 path；多 endpoint 由调用方传不同 URL 解决。

---

## 10. 后续步骤

评审通过后，使用 **writing-plans** 技能输出实现计划（文件组织、命名、`httpx` 异步/同步选择、与现有 `httpx` 超时配置是否复用 `Settings` 等——若复用 `Settings`，仅允许在 **工厂函数** 或 **调用方** 注入超时，避免 `paddleocr` 直接依赖 `app.config`；首选 **调用方传入 `timeout` / `client`** 以保持模块无全局配置依赖）。
