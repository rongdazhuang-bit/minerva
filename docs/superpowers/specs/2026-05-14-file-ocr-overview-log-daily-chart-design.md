# 文件 OCR「概览」按日日志统计折线图设计说明

**日期**：2026-05-14  
**状态**：已实现（2026-05-18 按代码回填；`schema_postgresql.sql` 仍滞后）  
**依赖**：现有 `ocr_file_log` 表与 ORM `OcrFileLog`（`backend/app/file_ocr/domain/db/models_log.py`）；现有概览页 `RulesFileOcrOverviewPage` 与 `GET .../ocr-files/overview-stats`；鉴权与 `require_workspace_member` 一致。

---

## 1. 目标与成功标准

- **目标**：在文件 OCR 概览（`/app/file-ocr/overview`）增加一张**折线图**：X 轴为**连续 30 个日历日**（服务器本地时区），Y 轴为**条数**；按 `ocr_file_log` 分别统计 **PaddleOCR** 与 **MinerU** 的**成功数**与**失败数**（共四条序列）。
- **成功标准**：任意 workspace 下，图上 30 个点与数据库在本文档「指标定义」下的聚合结果一致；无数据日显示为 0；权限与现有 OCR 文件接口一致；中英文文案走 i18n。

---

## 2. 指标定义（与实现语义一致）

以下均在 **`workspace_id = :ws`** 的 `ocr_file_log` 上计算。

| 概念 | 定义 |
|------|------|
| 统计时点 | 使用列 **`start_at`**。与当前日志列表 API 一致：列表中将 `start_at` 映射为响应字段 `create_at`；本文档中用户口头「按 create_at」**落实为 `start_at`**。若将来表增加真实 `create_at` 且产品要求切换，可另开变更；本规格默认 **`start_at`**。 |
| 日历日与窗口 | 使用**服务器本地时区**：从「今天」所在日期起，向前共 **30 个自然日**（**含今天**）。日界为本地 `00:00:00`；时间范围为 **第 30 天 00:00:00（含）至「明天」00:00:00（不含）** 左闭右开，避免边界漏计。 |
| X 轴补点 | **固定 30 个点**：按日期升序；若某日无任何计入序列的日志，该日四个计数均为 **0**，仍输出该日。 |
| PaddleOCR 成功数 | `ocr_type = 'PADDLE_OCR'` 且 `status = 'SUCCESS'`（常量见 `FILE_OCR_LOG_STATUS_SUCCESS`）。 |
| PaddleOCR 失败数 | `ocr_type = 'PADDLE_OCR'` 且 `status = 'FAILED'`。 |
| MinerU 成功数 | `ocr_type = 'MINERU'` 且 `status = 'SUCCESS'`。 |
| MinerU 失败数 | `ocr_type = 'MINERU'` 且 `status = 'FAILED'`。 |
| RUNNING | `status = 'RUNNING'` **不计入**上述成功/失败序列（该日可能仅 RUNNING，则四条线在该日均为 0）。 |
| 其它 `ocr_type` | 不计入四条线（若存在未来扩展类型，默认忽略）。 |

**时区实现说明**：以进程可用的**系统本地时区**为准（部署上应保证容器/主机 `TZ` 或等价配置与「服务器本地」预期一致）。在应用层用 Python `datetime` + `zoneinfo`（或等价）生成 30 天日期列表与窗口边界，避免依赖数据库会话 `TimeZone` 隐式行为导致环境差异。

---

## 3. API 设计

- **方法 / 路径**：`GET /workspaces/{workspace_id}/ocr-files/overview-log-daily-stats`（与现有 `overview-stats` 并列，**不修改**既有 `OcrFileOverviewStatsOut` 契约）。
- **鉴权**：`get_current_user` + `require_workspace_member(workspace_id)`，与 `get_ocr_file_overview_stats` 一致。
- **查询参数**：首版**无**（窗口固定最近 30 天）；若后续需要 `days` 或 `end_date`，另开规格。
- **响应体（建议）**：

| 字段 | 类型 | 含义 |
|------|------|------|
| `items` | array，长度 **30** | 按 `date` **升序** |
| `items[].date` | string | `YYYY-MM-DD`（服务器本地日历日） |
| `items[].paddle_success` | int | 当日 PaddleOCR 成功条数 |
| `items[].paddle_failed` | int | 当日 PaddleOCR 失败条数 |
| `items[].mineru_success` | int | 当日 MinerU 成功条数 |
| `items[].mineru_failed` | int | 当日 MinerU 失败条数 |

字段命名实现阶段可与前端对齐微调，但语义须与上表一致。

**实现策略（推荐）**：SQL 按日 + `ocr_type` + `status` 聚合得到**稀疏**结果；Python 生成连续 30 天并与稀疏结果 merge，缺日填 0。避免拉全量明细行。

**性能**：若生产上 `(workspace_id, start_at)` 组合查询偏慢，评估新增 btree 索引；与现有 `ix_ocr_file_log_file_start (ocr_file_id, start_at)` 用途不同，不互相替代。

**错误**：沿用工作空间成员校验的既有 HTTP 语义。

---

## 4. 前端设计（`RulesFileOcrOverviewPage`）

- **位置**：现有四个 KPI `Statistic` 卡片**下方**新增 `Card`，内嵌折线图。
- **数据**：`useQuery` 调用新接口；`enabled: Boolean(workspaceId)`；加载 Spin、错误 `Alert` 与概览现有模式一致。
- **图表**：当前 `minerva-ui` 无通用图表依赖，实现阶段**新增**一种图表库（候选：**Recharts** 或 **ECharts**；以 bundle 体积与 Ant Design 6 兼容性在实现计划中敲定）。同一图内 **4 条 Line**，图例区分四条序列。
- **国际化**：卡片标题、图例、空提示等使用 `zh-CN.json` / `en.json` 键值，禁止硬编码中文。

---

## 5. 测试

- **后端**：固定「当前时间」与本地时区（测试中 patch 或使用 `freezegun` 等），写入 `ocr_file_log` 若干行（跨日边界、`PADDLE_OCR`/`MINERU`、SUCCESS/FAILED/RUNNING 混合）；断言返回 `items` 长度 30、缺日为零、计数与手工预期一致。
- **前端**：可选组件测试；至少保证在固定 Mock 下四条线与 X 轴日期正确渲染（可在实现计划中约定）。

---

## 6. 范围外

- 可配置天数、可下载 CSV、按小时聚合、RUNNING 单独曲线、跨 workspace 看板。
- 首版不强制新增配置项 `FILE_OCR_STATS_TZ`；若部署时区与预期不符，可作为后续增强。

---

## 7. 风险与对齐项

- 仓库内 `backend/sql/schema_postgresql.sql` 中 `ocr_file_log` 片段可能与 ORM/真实迁移**不一致**；开发与上线前以 **ORM 与真实库结构**为准。若生产仍使用历史 `Y/N/P` 状态枚举，须在产品与研发间对齐映射后再实现本规格。

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-14 | 初版：头脑风暴确认后定稿。 |
| 2026-05-18 | 按代码回填实现对照 §9。 |

---

## 9. 实现对照（以代码为准，2026-05-18）

| 项 | 代码 |
|----|------|
| API | `GET .../ocr-files/overview-log-daily-stats`（30 天四序列） |
| ORM | `OcrFileLog`：`start_at`/`finish_at`/`ocr_type`/`RUNNING\|SUCCESS\|FAILED` |
| UI | `FileOcrTaskPage.tsx` 内 `RulesFileOcrOverviewPage` + Recharts |
| **文档滞后** | `schema_postgresql.sql` 中 `ocr_file_log` 仍为旧列/旧状态注释 |
