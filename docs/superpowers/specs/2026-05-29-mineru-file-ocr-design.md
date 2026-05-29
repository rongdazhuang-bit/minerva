# MinerU 文件 OCR（配置 + 同步 `/file_parse`）设计说明

**日期**：2026-05-29  
**状态**：已实现（2026-05-29 按代码回填）  
**依据**：[MinerU Quick Usage — FastAPI](https://opendatalab.github.io/MinerU/usage/quick_usage/)（`POST /file_parse`、`POST /tasks`）；仓库内 Paddle 参考：`backend/app/file_ocr/service/strategies/paddle.py`、`backend/app/ocr/paddleocr/`、`minerva-ui/src/features/settings/ocr/paddleOcrParams.ts`。

---

## 1. 目标与边界

### 1.1 目标

1. **OCR 工具（设置页）**：将 MinerU 的 `ocr_config` 替换为自部署 `mineru-api` 的 form 参数字段（snake_case），并提供对应表单与只读展示。
2. **OCR 任务（写路径）**：实现 `MineruFileStrategy`，流程与 Paddle 对齐：S3 取源文件 → 合并工具配置 → HTTP 调用 → 按页写入 `ocr_file_mineru` → 更新 `ocr_file` 为 `SUCCESS`。
3. **启用扫描**：将 `MINERU` 加入 INIT 扫描白名单，使 MinerU 任务可被 Celery `file_ocr.scan_init` 认领执行。

### 1.2 本期范围

| 项 | 本期 | 说明 |
|----|------|------|
| 同步 `POST /file_parse` | **实现** | 阻塞至 MinerU 返回最终结果 |
| 异步 `POST /tasks` + 轮询 | **占位** | URL 以 `/tasks` 结尾时明确失败，不静默降级 |
| `layout_blocks_json` | **留空** | 首期仅持久化 `markdown_text`、`markdown_images`、页图；LDM 适配后续独立做 |
| 旧版 MinerU 云端参数 | **移除** | `is_ocr`、`callback`、`data_id` 等自部署 API 不使用的键不再出现在 UI |

### 1.3 成功标准

- 工作区配置 MinerU 工具（URL 如 `http://host:8000/file_parse`）并保存 16 项参数后，创建 `ocr_type=MINERU` 任务，worker 执行成功后：
  - `ocr_file.status = SUCCESS`，`page_count` 正确；
  - `ocr_file_mineru` 按页有 `markdown_text`（及可选 `markdown_images`）；
  - 详情 Drawer / `markdown-pages` 可读；
  - PDF/图像源文件有 `page_raster_object_key`（与 Paddle 一致）。
- URL 以 `/tasks` 结尾时任务 `FAILED`，`remark` 含 `mineru_async_not_implemented`。

---

## 2. 架构：镜像 Paddle 分层、独立解耦

与 Paddle 采用 **相同分层模式**，模块间 **不交叉依赖**（MinerU 客户端不读 ORM；Paddle 模块不引用 MinerU）。

```text
minerva-ui/settings/ocr/
  mineruParams.ts              # ocr_config ↔ 表单
  PaddleOcrParamsTab.tsx       # MineruOcrParamsFields / Readonly

backend/app/ocr/mineru/        # 纯 HTTP + Pydantic（无 DB）
  schemas.py
  errors.py
  client.py                    # post_file_parse(multipart)

backend/app/file_ocr/service/
  mineru_ocr_request.py        # SysOcrTool.ocr_config + 运行时 file → form
  mineru_result_parse.py       # ZIP/JSON → 按页结构
  strategies/mineru.py         # 编排：S3、HTTP、落库、状态
  ocr_http_headers.py          # 复用（鉴权头）
  s3_object_bytes.py           # 复用
  paddle_markdown_images.py    # 复用或抽公共 inline 逻辑（仅调用，不耦合 Paddle 策略）
```

**依赖规则**（与 `app/ocr/paddleocr` 一致）：

| 层 | 允许依赖 | 禁止依赖 |
|----|----------|----------|
| `app/ocr/mineru/` | 标准库、`httpx`、`pydantic` | `sqlalchemy`、`SysOcrTool`、`file_ocr` |
| `file_ocr/service/mineru_*.py` | `app/ocr/mineru`、`SysOcrTool`、`OcrFile` | `app/ocr/paddleocr` 策略内部 |
| `strategies/mineru.py` | 上述 service + layout 页图 | 直接 httpx 大段内联 |

---

## 3. API 模式：由 URL path 推断

| `SysOcrTool.url`（完整 URL，含 path） | 行为 |
|--------------------------------------|------|
| 以 `/file_parse` 结尾 | 同步阻塞：multipart POST，等待响应体（ZIP 或 JSON） |
| 以 `/tasks` 结尾 | **占位**：`NotImplementedError` → `ocr_file` `FAILED`，remark `file_ocr:mineru_async_not_implemented` |
| 其他 path | 校验失败 → `FAILED`，remark 说明需 `/file_parse` 或 `/tasks` |

**不**在 `ocr_config` 中增加 `call_mode` 字段；模式完全由 URL 决定。

### 3.1 异步占位（后续扩展，本期仅文档）

后续实现时预期：

- `ocr_file` 增加 `vendor_task_id`（及可选 poll URL 字段或 JSONB `vendor_state`）；
- 新增 Celery 任务 `file_ocr.mineru_poll`（`sys_celery` 定时）；
- `scan_init` 在「已提交、未完结」时不将 `ocr_file_log` 标为 SUCCESS。

本期代码仅保留 `/tasks` 分支 stub，不建表、不注册 beat。

---

## 4. OCR 工具配置（`ocr_config`）

键名与 MinerU FastAPI **multipart form** 字段一致，**snake_case** 持久化于 `sys_ocr_tool.ocr_config`（JSONB）。

| 键 | 类型 | 传 API | UI 默认 | 说明 |
|----|------|--------|---------|------|
| `output_dir` | string | **是** | `./output` | 有值则写入 form；默认 `./output` |
| `lang_list` | string[] | 是 | `["ch"]` | 至少一项；form 重复键或数组按 MinerU 服务端约定 |
| `backend` | string | 是 | `hybrid-auto-engine` | 如 `pipeline`、`vlm-auto-engine`、`*-http-client` |
| `parse_method` | string | 是 | `auto` | `auto` / `txt` / `ocr` |
| `formula_enable` | boolean | 是 | `true` | form 值为 `true`/`false` 字符串 |
| `table_enable` | boolean | 是 | `true` | 同上 |
| `server_url` | string \| null | 是（非空时） | 空 | `backend` 为 `*-http-client` 时 **必填** |
| `return_md` | boolean | 是 | `true` | |
| `return_middle_json` | boolean | 是 | `true` | 便于按页拆分 |
| `return_model_output` | boolean | 是 | `false` | |
| `return_content_list` | boolean | 是 | `false` | |
| `return_images` | boolean | 是 | `true` | |
| `response_format_zip` | boolean | 是 | `true` | 默认 ZIP 响应 |
| `start_page_id` | integer | 是 | `0` | 0-based |
| `end_page_id` | integer \| null | 是 | null → 传 `99999` | 与 MinerU 官方 client 对齐 |

**序列化约定**：

- 布尔：`str(value).lower()` → `"true"` / `"false"`。
- `end_page_id` 为 `null` 或未配置时，请求 form 传 `"99999"`。
- `output_dir`：未配置时使用默认 `./output` 并 **始终** 传入 form（除非未来显式支持「不传则服务端默认」开关；本期默认即传）。
- 运行时 **禁止** 从 `ocr_config` 覆盖 multipart 的 `files` 字段。

**校验**（保存工具或 worker 执行前）：

- `backend.endswith("http-client")` 且 `server_url` 为空 → 失败。
- `lang_list` 为空数组或未配置 → 请求 form 使用 `["ch"]`（与 MinerU 官方 client 一致）。

**旧配置兼容**：读取旧 `ocr_config` 时忽略未知键；编辑保存后写入新 schema。不自动迁移旧键到新键。

---

## 5. 同步任务流程（`MineruFileStrategy`）

与 `PaddleOcrFileStrategy.process` 步骤对齐：

```text
1. 校验 tool.url 非空且 path 为 /file_parse
2. read_workspace_object_bytes(workspace_id, object_key)
3. mineru_ocr_request.build_file_parse_form_for_tool(tool) → form dict
4. multipart: files=(file_name, bytes, mime) + form 字段
5. build_ocr_tool_http_headers(tool)
6. app.ocr.mineru.client.post_file_parse(url, ...)
7. mineru_result_parse.parse_response(body, content_type) → List[MineruPageResult]
8. rasterize_source_file + upload_page_rasters（复用 layout.page_raster）
9. DELETE 旧 ocr_file_mineru 行（同 workspace + file_id）
10. INSERT 每页 OcrFileMineru（layout_blocks_json=null, layout_version=settings.layout_schema_version）
11. ocr_file.page_count, status=SUCCESS, remark=null
```

**HTTP 客户端**（`app/ocr/mineru/client.py`）：

- `POST` 至调用方提供的完整 URL（不改写 path）。
- 超时：connect 10s，read/write 300s（与 Paddle 默认同量级，可常量配置）。
- 非 2xx → `MineruTransportError`；响应体无法解析 → `MineruParseError`。
- INFO 日志对文件二进制与 ZIP 内容做 redaction（参考 Paddle client）。

---

## 6. 响应解析（`mineru_result_parse.py`）

### 6.1 ZIP（`response_format_zip=true`，默认）

1. 安全解压（防 `..` path traversal，参考 MinerU `safe_extract_zip`）。
2. 定位文档目录：单文件任务通常 `{stem}/` 下含 `{stem}.md`、`{stem}_middle.json`、`images/`。
3. **按页**：
   - 优先：`middle.json` → `pdf_info[]`，每元素 `page_idx` 对应一页 markdown 片段（从 md 或 middle 结构提取）。
   - 回退：整份 `.md` 作为 `page_index=0` 单页。
4. **图片**：ZIP 内 `images/*` 相对路径 → 读 bytes → data URI 写入 `markdown_images` JSON（与 Paddle inline 语义一致）。
5. **`page_width` / `page_height`**：middle.json 有则取，否则 `null`。

### 6.2 JSON（`response_format_zip=false`）

解析 JSON 体中的 md / middle / images 字段（以实现阶段 MinerU 实际响应为准）；若结构不支持按页，整文档单页落库。

### 6.3 首期不写入

- `layout_blocks_json`：**始终 `null`**（LDM / `from_mineru.py` 后续 spec）。
- `return_model_output` / `return_content_list` 的原始大块：**不落库**（仅用于解析 md 的中间步骤，不建结果表列）。

---

## 7. 扫描与常量

- `FILE_OCR_SUPPORTED_SCAN_OCR_TYPES`：由 `frozenset({"PADDLE_OCR"})` 扩展为包含 `"MINERU"`。
- `scan_init` 逻辑 **不变**（同步路径下一次 `process()` 内完成）。
- 重试：现有 `retry` API 清 `ocr_file_mineru` 后重置 `INIT`，行为与 Paddle 一致。

---

## 8. 前端（minerva-ui）

### 8.1 `mineruParams.ts`

- 重写：`defaultMineruFormValues`、`ocrConfigToMineruFormValues`、`mineruFormValuesToOcrConfig`。
- 常量：`MINERU_BACKEND_OPTIONS`、`MINERU_PARSE_METHOD_OPTIONS`、`MINERU_LANG_OPTIONS`（与 MinerU CLI 文档对齐的可选值）。
- `output_dir` 默认 `./output`；保存时若无用户输入仍写入默认值。

### 8.2 `PaddleOcrParamsTab.tsx`

- 替换 `MineruOcrParamsFields` / `MineruOcrParamsReadonly` 字段列表。
- 布局：与 Paddle 相同 `Row`/`Col`、`allowClear`、`triBoolSelect`（三态布尔）。
- `lang_list`：`Select mode="multiple"`；`server_url` 在 `backend` 含 `http-client` 时表单必填。

### 8.3 i18n

- 更新 `settings.ocrMineru.*`（`en.json` / `zh-CN.json`），删除旧云端参数字符串。

---

## 9. 错误处理

| 场景 | `ocr_file.status` | `remark` 示例 |
|------|-------------------|---------------|
| URL 为空 | FAILED | `file_ocr:empty_tool_url` |
| URL 为 `/tasks` | FAILED | `file_ocr:mineru_async_not_implemented` |
| URL path 非法 | FAILED | `file_ocr:mineru_invalid_url_path` |
| http-client 缺 server_url | FAILED | `file_ocr:mineru_missing_server_url` |
| HTTP 4xx/5xx | FAILED | `file_ocr:MineruTransportError:...` |
| ZIP/JSON 解析失败 | FAILED | `file_ocr:MineruParseError:...` |
| 成功 | SUCCESS | `null` |

`ocr_file_log`：同步成功/失败与 Paddle 相同，在 `scan_init._process_one_claimed` 内 finalize。

---

## 10. 测试

| 模块 | 用例 |
|------|------|
| `mineru_ocr_request` | 默认 `output_dir`；`end_page_id` null → `99999`；禁止覆盖 `files`；http-client 校验 |
| `mineru_result_parse` | fixture ZIP → 多页 markdown + images |
| `app/ocr/mineru/client` | mock httpx：multipart 字段、超时、非 2xx |
| `MineruFileStrategy` | mock client + DB：SUCCESS 落库；`/tasks` URL → FAILED |
| UI | `mineruFormValuesToOcrConfig` 往返 |

---

## 11. 实现对照（以代码为准，2026-05-29）

| spec 条目 | 代码位置 | 备注 |
|-----------|----------|------|
| MinerU HTTP 客户端 | `backend/app/ocr/mineru/` | `client.py`、`errors.py`、`schemas.py` |
| form 合并 | `backend/app/file_ocr/service/mineru_ocr_request.py` | `build_file_parse_form_for_tool`、`resolve_mineru_url_mode` |
| 响应解析 | `backend/app/file_ocr/service/mineru_result_parse.py` | ZIP/JSON → `MineruPageResult` |
| 写策略 | `backend/app/file_ocr/service/strategies/mineru.py` | 同步 `/file_parse` 全流程 |
| 扫描白名单 | `backend/app/file_ocr/constants.py` | `MINERU` 已加入 |
| 设置页参数 | `mineruParams.ts`、`PaddleOcrParamsTab.tsx`、i18n | 16 项参数 |
| 单测 | `backend/tests/test_mineru_*.py` | request/parse/client/strategy |
| 异步 `/tasks` | `strategies/mineru.py` | 占位 `NotImplementedError` |
| LDM layout | — | 非本期，`layout_blocks_json` 恒为 null |

---

## 12. 非目标（本期不做）

- MinerU `middle.json` → `layout_blocks_json` / `from_mineru.py`。
- 异步 `/tasks` 提交、轮询 Celery、`vendor_task_id` 表字段。
- 修改 `ocr_file` 状态枚举或前端四态 UI。
- 环境变量变更（无新增 `app/config.py` 项；MinerU 服务地址由工具 URL 配置）。
