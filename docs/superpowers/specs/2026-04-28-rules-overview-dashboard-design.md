# 规则库「概览」统计仪表盘设计说明

**日期**：2026-04-28  
**状态**：已确认，待实现  
**依赖**：`rule_base` 工作空间隔离与现有字典 **`RULE_ENG_SUBJECT_DOC`**（三级：`engineering_code` / `subject_code` / `document_type`）；前端已有 `scopeTriple.ts`、`listDicts(..., { code: 'RULE_ENG_SUBJECT_DOC' })` 与 `buildCodeNameMap`。

---

## 1. 目标与成功标准

- **后端**：在成员上下文中对当前 **`workspace_id`** 的 `rule_base` 提供只读聚合：规则总条数；三个维度上「非空编码」的 **distinct code 列表**（以及与之一致的计数，便于校验）。
- **前端**：替换 `RulesOverviewPage` 占位；展示四个 KPI（**工程（项目）**、**专业**、**文档类型**、**规则**）；并提供 **简要分项**：按维度列出工作中出现的编码及 **字典名称**（名称来自既有字典接口 + `buildCodeNameMap`，无名称时回显 **code**）。
- **术语**：用户口头「项目」= **工程**，对应 **`engineering_code` 去重**。
- **成功标准**：数字与列表与数据库聚合一致；权限与 **`GET .../rule-base`** 列表一致；分项文案不以裸 code 作为唯一信息（至少副标题或同一行给出字典名称）。

---

## 2. 指标定义（与 SQL 语义一致）

以下均在 **`workspace_id = :ws`** 的 `rule_base` 上计算。

| 指标 | 定义 |
|------|------|
| 规则条数 | `COUNT(*)` |
| 工程（项目）数 | `COUNT(DISTINCT engineering_code)`，且 `engineering_code` 经 trim 后非空 |
| 专业数 | `COUNT(DISTINCT subject_code)`，且 `subject_code` trim 后非空 |
| 文档类型数 | `COUNT(DISTINCT document_type)`，且 `document_type` trim 后非空 |

**说明**：列为 `NULL` 或空串的字段不参与对应维度的 distinct 集合；该行仍计入「规则条数」。

---

## 3. API 设计

- **方法 / 路径**：`GET /workspaces/{workspace_id}/rule-base/overview-stats`（与现有 `rule-base` 前缀并列，挂在同一 `RuleBase` 路由模块下）。
- **鉴权**：`get_current_user` + `require_workspace_member(workspace_id)`，与列表端点一致。
- **响应体（建议字段名，实现可微调）**：

| 字段 | 类型 | 含义 |
|------|------|------|
| `rule_count` | int | 规则总条数 |
| `engineering_codes` | string[] | 非空 distinct `engineering_code`，**排序规则**：按 UTF-8 字符串升序（与 `ORDER BY` 一致） |
| `subject_codes` | string[] | 非空 distinct `subject_code`，同上 |
| `document_type_codes` | string[] | 非空 distinct `document_type`，同上 |

**说明**：三个 count 可由 `len(相应数组)` 得出；若服务端同时返回冗余的 `*_count` 整数，须与数组长度一致，避免分歧。

**错误**：沿用工作空间成员与资源不存在时的既有 HTTP 语义（403 / 404 等）。

---

## 4. 前端设计（`RulesOverviewPage`）

### 4.1 数据请求

- **并行**：`overview-stats` + `listDicts(workspaceId, { code: 'RULE_ENG_SUBJECT_DOC', page_size: ... })`（或项目内已封装的一键拉树方法，与规则列表一致），构建 `Map<code, name>`（`buildCodeNameMap` 展平树或扁平列表均可，与列表页同源逻辑优先）。
- **展示行格式**：优先 **`名称 (code)`** 或 **`名称`**，tooltip 带 code；若 `name` 缺失则仅 **code**（与 `formatScopeTriplePathLabel` 回退策略一致）。

### 4.2 布局

- **顶部**：四个 KPI 卡片（工程数、专业数、文档类型数、规则数）；数字取自响应或 `len(codes)` + `rule_count`。
- **分项**：三个区块（工程 / 专业 / 文档类型），每区标题 + 该维 code 列表的简要展示（`List` / `Tag` / `Descriptions` 等，与现有规则页视觉一致）。列表仅含 **stats 返回的 codes**，不展示字典中未出现在规则里的项。
- **空态**：无规则时 KPI 多为 0，分项可为空描述；加载与错误态与项目内其它数据页一致。

### 4.3 国际化

- 新增/复用 `nav.rulesOverview`、占位符替换后的说明文案；卡片标题使用中英文资源文件键，避免硬编码中文。

---

## 5. 测试

- **后端**：对工作空间写入若干 `rule_base` 行（含空码、重复码、trim 边界）；断言 `rule_count` 与三个数组内容与 SQL 手工结果一致。
- **前端**：组件测试或 Story 可选；至少保证在固定 Mock 下 KPI 与分项名称解析正确。

---

## 6. 范围外

- 不按时间维度的趋势图、导出；不跨 workspace 聚合；不在本接口内返回字典全文（字典仍由字典 API 提供）。

---

## 7. 实现阶段衔接

规格审阅通过后，使用 **writing-plans** 产出实现计划（后端路由 + service 聚合查询 + 前端页面与 API 封装 + 测试）。
