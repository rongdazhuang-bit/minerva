# 专业领域文档校审系统（LLM + 多格式 + 批注）设计说明

**日期**：2026-08-24  
**状态**：设计已确认；实现计划见 `docs/superpowers/plans/2026-08-24-domain-document-review.md`（P0–P3）  
**范围**：独立产品方案——多场景智能校审（合同 / 错别字 / 法律文书 / 规则 / 以文审文 / 全文一致性）；多格式解析；doc/docx/pdf 批注写回；审核内容条款入库与初始化；校审可观察性。  
**非绑定**：本 spec 描述目标架构与契约，不要求复用某一既有业务模块路径；实现时可参考同类「解析 → 异步任务 → 产物下载」模式，但以本文为准。

---

## 1. 目标与成功标准

### 1.1 目标

- 以 **LLM + 确定性规则** 结合，提供专业领域文档校审能力。
- **六条产品线独立入口**，共享统一底座（解析、引擎、批注、内容包、可观察性）。
- 支持输入格式：**md / txt / excel（xls/xlsx）/ doc / docx / pdf**。
- 校审完成后，对 **doc / docx / pdf** 在原文对应位置写入 **批注（Comment / Annotation）**；其余格式输出问题报告（excel 可用结果 sheet）。
- **审核内容条款可入库、可种子初始化、发布版本锁定进任务**，保证可复现。
- **校审全过程可观察**：事件时间线、指标、追踪、任务详情面板。



### 1.2 成功标准

- 用户按产品线上传文件（以文审文需主文 + 依据文），任务异步完成；可查看 Finding 列表与阶段时间线。

doc/docx/pdf 成功任务可下载带批注文件；批注可追溯到 `finding_id` / 规则或清单项。

md/txt/excel 成功任务可下载结构化报告；excel 含「校审结果」sheet 或等价列。

任务创建时锁定 `pack_release_id`；历史任务按锁定版本复盘，不受后续条款编辑影响。

任务详情可见：当前 Stage、事件时间线、LLM 次数/token/耗时、finding 按 severity 汇总、批注 written/unanchored/failed 计数、内容包版本。

- 数据表 **无库级外键、无 ON DELETE 级联**；删除在业务层显式清理子表与对象存储。



### 1.3 已确认决策


| 项        | 决策                                          |
| -------- | ------------------------------------------- |
| 「批准」含义   | **批注**（Word Comment / PDF Annotation），非审批流  |
| 产品形态     | **分场景独立产品线**（B）                             |
| 总体架构     | **插件化校审引擎**（统一底座 + Profile 组装 Stage）        |
| 合同 vs 法律 | 同一 L3 领域引擎 + 不同 `domain_pack`               |
| doc 批注   | **先转 docx** 再写 Comment；交付 docx（再转回 doc 为可选） |
| 正文改写     | **首期不做**自动改稿，只批注/报告                         |
| 内容包      | 种子初始化 + 发布版本锁定；**在线编辑 draft 为二期**           |
| 可观察性     | 事件时间线 + 指标 + 追踪 + 任务详情四块面板为 **首期必做**        |




### 1.4 非目标（首期）

- 图纸校审、在线协同编辑与「一键采纳批注改正文」。
- Excel / md / txt 原生批注；doc 不经转换的原生批注。
- 多智能体辩论式校审。
- 内容包在线可视化编辑与审批发布流（二期）。
- SSE 进度推送（首期 HTTP 轮询即可）。
- 扫描 PDF 的复杂版式重建（需要时先 OCR 出文字层再校审）。

---



## 2. 能力分类（L1–L5）与产品线映射


| 层级  | 归类   | 覆盖场景    | 本质                   |
| --- | ---- | ------- | -------------------- |
| L1  | 语言层  | 错别字校审   | 字词、标点、基础语病           |
| L2  | 规则层  | 规则校审    | 可配置硬/软规则             |
| L3  | 领域语义 | 合同、法律文书 | 要素抽取 + 领域清单 + LLM 研判 |
| L4  | 对照   | 以文审文    | 主文 vs 依据文双文档对齐比对     |
| L5  | 一致性  | 全文一致性   | 文内实体/数值/称谓/条款引用自洽    |



| 产品线 Profile   | 默认 Stage 装配                                 |
| ------------- | ------------------------------------------- |
| `typo`        | `typo_l1`                                   |
| `rule`        | `rule_l2`                                   |
| `contract`    | `domain_l3(contract)` → 可选 `consistency_l5` |
| `legal`       | `domain_l3(legal)` → 可选 `consistency_l5`    |
| `text2text`   | `compare_l4`                                |
| `consistency` | `consistency_l5`                            |


共享底座：多格式解析 → `DocumentIR` → Review Engine → Finding 合并 → 批注写回 / 报告导出 → 可观察性贯穿。

---



## 3. 总体架构（方案 B：插件化校审引擎）



### 3.1 方案对比与选择


| 方案           | 思路                      | 结论           |
| ------------ | ----------------------- | ------------ |
| A. 六条独立流水线   | 每场景一套解析→LLM→写回          | 重复多，不采纳      |
| **B. 插件化引擎** | 统一底座 + Profile 组装 L1–L5 | **采纳**       |
| C. 多智能体编排    | 每检查点一 Agent             | 成本高、难控，首期不采纳 |




### 3.2 系统上下文

```text
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Client UI  │────▶│  API             │────▶│  Job Orchestrator│
│ 六产品线入口 │     │  创建/查询/下载    │     │  (异步 Worker)   │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
        ┌───────────────┬───────────────┬─────────────┼──────────────┐
        ▼               ▼               ▼             ▼              ▼
 ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐
 │ Ingest &   │  │ Review     │  │ Content  │  │ LLM      │  │ Annotation │
 │ Parse      │  │ Engine     │  │ Registry │  │ Gateway  │  │ Writer     │
 └────────────┘  └────────────┘  └──────────┘  └──────────┘  └────────────┘
        │               │                              │
        └───────────────┴──────────────────────────────┘
              Object Store + DB + Observability Fabric
```



### 3.3 逻辑模块目录（实现时命名可微调）

```text
review-system/
├── api/
├── ingest/          # 检测、多格式 → DocumentIR
├── engine/
│   ├── runtime      # 按 Profile 调度 Stage
│   ├── stages/      # typo_l1, rule_l2, domain_l3, compare_l4, consistency_l5
│   └── merge
├── packs/           # Content Registry：种子、发布、加载
├── llm/             # 网关、schema、重试、usage
├── annotate/        # docx comments, doc bridge, pdf annotations
├── export/          # md/txt/excel 报告
├── jobs/            # 任务模型与 Worker
└── observability/   # events、metrics、tracing 封装
```

---



## 4. 核心中间模型



### 4.1 `DocumentIR`

```text
DocumentIR {
  doc_id, source_name, format,   # md|txt|xls|xlsx|doc|docx|pdf
  blocks: Block[],
  structure?: SectionTree,
  meta?: { page_count, ... }
}

Block {
  block_id, text,
  kind: paragraph|heading|table_cell|list_item|header|footer,
  anchor: Anchor,
  order: int
}

Anchor (discriminated by format) {
  | { type: docx, paragraph_index, run_start?, run_end? }
  | { type: pdf,  page, quad_or_rect, char_start?, char_end? }
  | { type: xlsx, sheet, row, col }
  | { type: text, line_start, line_end }
}
```



### 4.2 `Finding`

```text
Finding {
  finding_id,
  profile_id, stage_id,
  severity: info|warn|error|critical,
  category: typo|rule|domain|compare|consistency,
  message, suggestion?,
  evidence: {
    primary: { doc_role: main|ref, block_id, quote },
    related?: [{ doc_role, block_id, quote }]
  },
  rule_id?, checklist_item_id?,
  confidence: 0..1
}
```



### 4.3 `ReviewProfile`

```text
ReviewProfile {
  id: typo|rule|contract|legal|text2text|consistency,
  display_name,
  inputs: { arity: 1|2+, roles: [main] | [main, reference+] },
  stages: StageRef[],
  packs: { rule_pack_ids?, domain_pack_id? },
  annotation: {
    enabled_formats: [doc, docx, pdf],
    comment_template,
    write_mode: always | on_confirm
  },
  llm: { model_policy, temperature, max_block_tokens }
}
```



### 4.4 Stage 契约

```text
Stage.run(ctx: ReviewContext) -> list[Finding]

ReviewContext {
  profile, packs,          # 已按 pack_release 锁定的快照
  docs: { role -> DocumentIR },
  prior_findings: Finding[],
  llm, options,
  obs: ObservabilityHandle # 打 event/metric/span
}
```

---



## 5. Stage 详细设计



### 5.1 L1 `typo_l1`

- 分块 → 可选词典/正则预检 → LLM 纠错 JSON → 映射 `block_id`。
- 专有名词误报通过 `TermWhitelist`（内容包）降低。
- 小模型优先；严格 schema：`wrong_span, suggest, reason`。



### 5.2 L2 `rule_l2`

- 硬规则：正则/禁用词/必含词，引擎内执行。
- 软规则：top-k 相关块 + LLM 判定 `pass|fail|uncertain`。
- Finding 必须带 `rule_id`；uncertain 默认 `warn`。
- 规则包为空时创建任务 **422**，禁止空跑。



### 5.3 L3 `domain_l3`（合同 / 法律共用）

- Phase A：按 pack 的 `extract_schema` 抽取 `DocumentProfile`。
- Phase B：checklist 逐项选相关块 + profile 片段研判。
- Phase C（可选）：调用 L5 子例程。
- 包内容：`extract_schema`、`checklist`、`system_prompt`、few-shot、关联条款引用。



### 5.4 L4 `compare_l4`

- 输入：`main` + `reference+`。
- 对齐：标题/条款号 + embedding 相似配对。
- 比对：遗漏 / 冲突 / 弱化 / 数值差。
- 批注只写主文；`related` 指向依据文摘录与位置。
- 长文：章节 Map → Reduce。



### 5.5 L5 `consistency_l5`

- 抽 `FactIndex`；同 key 多值确定性冲突；跨段语义矛盾走 LLM。
- Finding 至少两个锚点；批注挂后出现位置并引用前证。



### 5.6 Finding 合并

- 近邻同 anchor 去重；冲突时 severity 取高；保留来源 `stage_id` 列表或主来源。

---



## 6. 文件格式与交付物


| 格式         | 解析            | 校审  | 交付物                                  |
| ---------- | ------------- | --- | ------------------------------------ |
| md / txt   | 行/段块          | ✓   | JSON/CSV/HTML 问题报告；可选另存批注版 docx（非必须） |
| xls / xlsx | 单元格块          | ✓   | 结果 sheet 或批注列；首期不做 Excel 原生批注        |
| doc        | 转 docx 后解析    | ✓   | docx + Comments（再转回 doc 可选）          |
| docx       | 段落/run 锚点     | ✓   | Word Comment                         |
| pdf        | 文本层；扫描件可先 OCR | ✓   | Annotation / 高亮 + Popup              |


**批注定位策略**

1. Finding → `block_id` → `Anchor`。
2. 精确 span 失败 → 段落级批注 + 摘录。
3. 单条定位失败不导致整单失败：`annotate_status=unanchored`，仍进报告。

---



## 7. 任务流水线与状态机

```text
1. 创建 Job(profile_id, files[], options)
2. 解析 Profile.packs → 锁定 pack_release_id 写入 Job
3. Ingest 存源文件 → Parse → DocumentIR
4. Engine 按 stages 执行 → Merge → 持久化 findings
5. Annotate（doc/docx/pdf）或 Export report（其它）
6. SUCCESS；客户端轮询下载
```

```text
PENDING → PARSING → REVIEWING → ANNOTATING → SUCCESS
                 ↘ FAILED（failed_stage + error）
                 ↘ CANCELLED
```

扫描 PDF 可在 `PARSING` 前插入 `OCR_RUNNING`。

**错误策略**


| 场景        | 策略                                        |
| --------- | ----------------------------------------- |
| 不支持格式     | 创建时 400                                   |
| 解析失败      | FAILED                                    |
| 单块 LLM 失败 | 跳过 + warning；失败块比例 > 阈值（建议 30%）则整单 FAILED |
| 批注写回失败    | findings 保留；可单独重试 ANNOTATING，不重跑校审        |
| LLM 预算耗尽  | 首期 FAILED + 明确原因                          |


---



## 8. 审核内容条款入库与初始化



### 8.1 资产类型


| 资产                  | 用途                      | 消费方        |
| ------------------- | ----------------------- | ---------- |
| ClauseTemplate      | 标准条款/要点/风险提示            | L3         |
| ChecklistItem       | 审核清单项                   | L3         |
| RuleItem            | 硬/软规则                   | L2         |
| DomainPack          | 聚合抽取 schema + 清单 + 条款引用 | L3 Profile |
| TermWhitelist       | 专名/术语                   | L1         |
| CompareDimension    | 对照维度                    | L4         |
| ConsistencyFactType | 一致性事实类型                 | L5         |




### 8.2 逻辑表（无库级 FK）

```text
content_pack
  id, code, name, kind,          # domain|rule|typo|compare|consistency
  scope: global|tenant, tenant_id?,
  status: draft|published|archived,
  version: int,
  created_at, published_at?

content_clause
  id, pack_id, code, title, body,
  category, tags, risk_level, note,
  sort_order, enabled

content_checklist_item
  id, pack_id, code, title, instruction,
  severity_default, related_clause_codes[],
  enabled, sort_order

content_rule_item
  id, pack_id, code,
  match_mode: hard|soft,
  pattern_or_prompt, scope_filter_json,
  severity, enabled

content_pack_release
  id, pack_id, version,
  snapshot_json_uri, checksum,
  published_by, published_at
```

删除/归档在业务层处理：禁止误删仍被默认 Profile 绑定的已发布包；或先切换绑定再归档。

### 8.3 初始化（Bootstrap）

```text
content_seeds/          # 仓库内版本化种子 YAML/JSON
  contract/v1/...
  legal/v1/...
  typo_terms/v1/...
  compare/v1/...
  consistency/v1/...
        │
        ▼
 SeedLoader（启动命令 / 安装向导）
   1. 读 manifest（pack_code + version）
   2. 按策略 upsert
   3. publish → 写 content_pack_release 快照
   4. Profile 默认绑定当前已发布 version
```


| 策略                    | 行为                 |
| --------------------- | ------------------ |
| `skip_if_exists`（默认）  | 已有同 code 包则不覆盖     |
| `merge_additive`      | 只追加缺失 code         |
| `replace_draft`       | 覆盖 draft，不动已发布版    |
| `publish_new_version` | 打新 version 并切换默认绑定 |


租户可将全局包克隆后本地化修改，不影响全局。

### 8.4 运行时绑定

- Job 创建时写入并锁定 `pack_release_id`（可多个：规则包 + 领域包）。
- Stage **只读**该 release 快照，不读可变 draft。
- 历史任务按锁定版本复盘。



### 8.5 管理能力（首期）

- 列表/查看已发布包与版本。
- 受策略保护的种子重新初始化。
- **二期**：在线编辑 draft → 发布新版本。

---



## 9. 校审可观察性



### 9.1 关联 ID（强制贯穿）

`trace_id`、`job_id`、`stage_id`、`pack_release_id`、`llm_call_id`、`finding_id`。

### 9.2 业务事件 `review_job_event`

```text
event_type:
  job.created | parse.started | parse.done |
  stage.started | stage.done | stage.failed |
  llm.call | llm.retry | llm.schema_fail |
  finding.emitted | merge.done |
  annotate.started | annotate.item_failed | annotate.done |
  job.succeeded | job.failed | job.cancelled |
  content_seed.applied   # 初始化可观察
```

字段：`id, job_id, trace_id, ts, level, event_type, stage_id?, duration_ms?, attrs_json`。  
禁止只打无结构纯文本；正文默认截断/hash（见 9.5）。

### 9.3 指标（最小集）

- `review_job_total{profile,status}`、`review_job_duration_seconds{profile,status}`
- `review_stage_duration_seconds{profile,stage}`、`review_stage_failures_total{profile,stage,reason}`
- `review_llm_calls_total{stage,model,result}`、`review_llm_tokens_total{stage,model,dir}`、`review_llm_latency_seconds{stage,model}`
- `review_findings_total{profile,stage,severity,category}`
- `review_annotate_total{format,result}`、`review_unanchored_ratio{profile,format}`
- `review_pack_bind_total{pack_code,version}`、`content_seed_apply_total{pack,result}`



### 9.4 追踪 Span 树

```text
review.job
 ├─ review.parse
 ├─ review.stage {stage}
 │   ├─ review.llm
 │   └─ review.chunk / review.checklist_item
 ├─ review.merge
 └─ review.annotate
```



### 9.5 日志与隐私

- JSON 结构化日志。
- `observability.payload_mode = hash | truncated | full`；生产默认 `truncated`。
- Prompt 存 template version + hash；完整 prompt 仅 debug 采样入对象存储。



### 9.6 任务详情面板（首期必做）

1. 进度条 + 当前 Stage
2. 事件时间线
3. 资源账单：LLM 次数、token、耗时、可选费用估算
4. 产出摘要：finding 按 severity、批注 written/unanchored/failed、内容包版本号



### 9.7 告警（建议）

- 某 profile 失败率超阈值；LLM schema_fail 突增；任务 P95 耗时超阈值；种子初始化失败。

---



## 10. 持久化（逻辑模型）

```text
review_job
  id, profile_id, status, progress, error,
  pack_release_ids (json/array), failed_stage?,
  created_by, created_at, trace_id, ...

review_job_file
  id, job_id, role(main|reference),
  file_name, format,
  source_uri, ir_uri?, annotated_uri?, report_uri?

review_finding
  id, job_id, stage_id, severity, category,
  payload_json,
  annotate_status: pending|written|unanchored|skipped

review_job_event
  （见 §9.2）

content_* / content_pack_release
  （见 §8.2）
```

**删除顺序（业务层）**：events → findings → files（含对象存储）→ job；内容包删除另有绑定校验，不随 job 级联。

---



## 11. API 草图


| 方法       | 路径                                 | 说明                                   |
| -------- | ---------------------------------- | ------------------------------------ |
| `POST`   | `/review/jobs`                     | profile_id + 文件 + 选项；锁定 pack_release |
| `GET`    | `/review/jobs`                     | 分页；可按 profile 筛                      |
| `GET`    | `/review/jobs/{id}`                | 状态、进度、产物、pack 版本、账单摘要                |
| `GET`    | `/review/jobs/{id}/findings`       | 分页/severity 过滤                       |
| `GET`    | `/review/jobs/{id}/events`         | 可观察时间线                               |
| `GET`    | `/review/jobs/{id}/download`       | artifact=annotated|report|source     |
| `POST`   | `/review/jobs/{id}/cancel`         | 取消                                   |
| `POST`   | `/review/jobs/{id}/retry-annotate` | 仅重试写回                                |
| `DELETE` | `/review/jobs/{id}`                | 业务层级联清理                              |
| `GET`    | `/review/content-packs`            | 已发布包列表                               |
| `POST`   | `/review/content-packs/seed`       | 受控重新初始化（管理端）                         |


六产品线共用 API，差异仅 `profile_id` 与前端入口；或以 `/review/{profile}/jobs` 薄封装。

---



## 12. 前端信息架构

```text
智能校审
├── 错别字校审      → typo
├── 规则校审        → rule（选规则包）
├── 合同校审        → contract
├── 法律文书校审    → legal
├── 以文审文        → text2text（主文 + 依据文）
└── 全文一致性      → consistency
```

共性：上传 → 任务列表 → 详情（Finding 表 + 四块可观察面板 + 下载）。

---



## 13. LLM 网关

- `complete(messages, response_schema, model_policy)`。
- Stage 级模型策略：L1 小模型，L3/L4 强模型。
- Schema 失败重试 1～2 次，再跳过块并记 `llm.schema_fail`。
- 审计：prompt 版本 hash、model_id、usage。

---



## 14. 测试策略

- Parser：各格式 fixture → 块数/锚点快照。
- Stage：fixture IR + mock LLM → Finding 断言。
- Merge / Annotate 读写回数量。
- Content seed：幂等 `skip_if_exists`；Job 锁定 release 后改 draft 不影响结果。
- Observability：关键路径必有 stage 事件与 LLM metric。
- E2E：每 Profile 至少一条金样例（可分期补齐）。

---



## 15. 实现分期建议（写入计划时可拆）


| 期次  | 内容                                                         |
| --- | ---------------------------------------------------------- |
| P0  | 底座：IR、Job、Parse（优先 docx/pdf/txt/md）、LLM 网关、事件时间线、指标骨架、种子加载 |
| P1  | typo + rule 两条产品线 + docx/pdf 批注 + 报告导出                     |
| P2  | domain_l3（contract/legal 包）+ consistency                   |
| P3  | text2text + excel/xls + doc 转换 + 告警看板                      |


具体排期以实现计划为准。

---



## 16. 自检摘要（spec 评审）

- 无 TBD/TODO 占位；「批准」已明确为批注。
- 合同/法律不拆双引擎，与 Profile 表一致。
- 内容包与可观察性已纳入首期必做边界；在线编辑明确二期。
- 单任务实现计划可覆盖 P0–P1；P2–P3 可同 spec 下分 plan 或同 plan 分里程碑。

