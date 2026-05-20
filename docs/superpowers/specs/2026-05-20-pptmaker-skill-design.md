# Agent `ppt` 技能（PPT Maker）：版式库 + Hybrid 选版生成设计说明

**日期**：2026-05-20  
**状态**：已实现（2026-05-20 按 spec 落地）  
**范围**：`backend/app/agent/skills/ppt/`（双工具流水线 + `pptmaker` 生成引擎 + 内置版式库资产）；Planner/Executor 经现有 `skill_loader` 集成。

**参考实现**：桌面 `AI生成PPT/AI生成PPT`（`test_generate_ppt.py`、`标准layout_P0P1版式库_layout_index.json`、`标准layout_P0P1版式库.pptx`、`layout_selection_usage.md`）。

**关系**：与 `file` 技能协作（沙箱读写大纲、图片、输出 pptx）；编排见 `2026-05-16-agent-langgraph-redesign-design.md`。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `backend/app/agent/skills/ppt/` 新增技能 id **`ppt`**（产品名 **PPT Maker**），并注册到 `skills/INDEX.md`。
- **双工具流水线**：
  1. `draft_ppt_outline` — 自然语言 → 结构化大纲 JSON（写入沙箱，可人工/Agent 二次编辑）。
  2. `generate_ppt` — 大纲 JSON → Hybrid 选版 → 填充占位符（含图片）→ 输出 `.pptx` 到沙箱。
- **版式库随 skill 打包**：`assets/template.pptx` + `assets/layout_index.json`（由参考「标准layout_P0P1版式库」迁入；索引字段与参考 JSON 一致）。
- **Hybrid 选版**：优先使用当前 Agent run 的 **同一 Chat 模型** 读 `layout_index` 语义字段选版；失败或置信度不足时回退 **规则映射**（与参考脚本一致）。
- 按页面内容形态（封面、N 要点、指标、多图、长正文、金句等）自动选择 Layout，并将文案映射到 placeholder `label`。

### 1.2 成功标准

- 用户说「帮我做一份关于 XX 的 PPT」→ Planner 路由到 `ppt` → 子 Agent 先 `draft_ppt_outline` 再 `generate_ppt`，返回沙箱内 `output/presentation.pptx` 路径及每页选版摘要。
- 用户提供现成大纲 JSON 或沙箱内 `outline.json` → 可直接 `generate_ppt`，无需 draft。
- `layout_mode=rule` 时无 LLM 亦可稳定生成（用于 CI/回归）；`layout_mode=hybrid` 时在模型可用时优先 AI 选版。
- 含 1–6 张图片的页面能选对版式，且图片从沙箱路径正确插入 picture placeholder。
- `GET .../agent/v2/skills` 列表含 `ppt`。

### 1.3 非目标（第一版不做）

- 用户上传**自定义** `.pptx` 版式库（沙箱覆盖 `assets/`）；后续可扩展 `template_path` 参数。
- 在线编辑已生成 pptx、动画/切换、演讲者备注、图表/ SmartArt、视频嵌入。
- 独立 REST「生成 PPT」API（仅 Agent 工具入口）。
- 在 Agent 工具中暴露 `extract_layout_index`（仅开发脚本/文档说明维护流程）。
- 参考脚本中的独立 `OPENAI_API_KEY` / `GEMINI_API_KEY` 选版通道（统一用 run 的 `chat_model`）。

---

## 2. 架构

### 2.1 目录结构

```text
backend/app/agent/skills/ppt/
├── SKILL.md
├── tools.py                      # register_tools(ctx) → draft + generate
├── assets/
│   ├── template.pptx             # 标准layout_P0P1版式库.pptx（实现时从参考目录复制）
│   └── layout_index.json         # 46 layouts，与参考 JSON 同 schema
└── pptmaker/
    ├── __init__.py
    ├── normalize.py              # slide 输入 → slide_spec
    ├── layout_select.py          # rule + LLM hybrid
    ├── fill.py                   # label → 文本；picture → 图片
    ├── generate.py               # 编排入口
    └── extract_layout_index.py   # 维护：pptx → layout_index.json
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| `SkillToolContext` | 扩展 `chat_model: BaseChatModel \| None`；`executor_node` 注入 `deps.model` |
| `ppt/tools.py` | LangChain `@tool`：`draft_ppt_outline`、`generate_ppt`；JSON ok/error 契约与 `file` skill 一致 |
| `pptmaker/generate.py` | 加载模板、删示例页、逐页 add_slide、save |
| `pptmaker/layout_select.py` | `select_layout_by_rule` + `select_layout_hybrid` |
| `pptmaker/fill.py` | `value_for_label`、图片插入 |
| `AgentFileSandbox` | 读大纲/图片、写 outline/json 与 output pptx |

### 2.3 数据流

```text
用户消息
  → Planner 匹配 ppt（SKILL.md 触发词）
  → executor: SkillToolContext(workspace_id, chat_model=deps.model)
  → ppt 子 Agent (ReAct)
       ├─ 无大纲: draft_ppt_outline(brief) → 沙箱 outlines/draft.json
       └─ generate_ppt(outline_path | outline) 
            → normalize 每页
            → hybrid/rule 选 layoutName
            → 填充 placeholders + 图片
            → 沙箱 output/presentation.pptx
  → 返回 pages[] 选版决策 + output_path
```

### 2.4 依赖

- `pyproject.toml` 增加 `python-pptx`（图片插入若需可读尺寸，可选 `Pillow`，按实现时评估）。

---

## 3. 大纲 Schema

### 3.1 单页 `slide_spec`（规范化后）

| 字段 | 类型 | 说明 |
|------|------|------|
| `pageTitle` | string | 页标题 |
| `items` | `{title?, body}[]` | 要点；金句可为单条仅 `body` |
| `keyNumbers` | `{number, label, desc?}[]` | 指标页；与 items 互斥时以 keyNumbers 为准 |
| `body` | string | 单段长正文 |
| `hasImage` | bool | 默认 `bool(images)` |
| `images` | `{path, caption?}[]` | **沙箱相对路径**；caption 填说明类 placeholder |

**兼容简写** `{title, content}`：多行按参考脚本拆分为 items / keyNumbers / body（`normalize.py` 移植 `test_generate_ppt.py` 逻辑）。

### 3.2 整份大纲

```json
{
  "meta": { "title": "封面主标题", "subtitle": "副标题" },
  "slides": [ /* slide_spec[] */ ]
}
```

- 若提供 `meta`，生成前可在 `slides` 首部插入封面页（`pageType=cover` → Layout「标题幻灯片」）。
- `draft_ppt_outline` 输出必须符合该 schema；服务端做 Pydantic 或等价校验。

---

## 4. 工具契约

### 4.1 `draft_ppt_outline`

| 参数 | 说明 |
|------|------|
| `brief` | 用户意图、素材要点（必填） |
| `slide_count` | 可选，期望页数上限提示 |
| `output_path` | 沙箱相对路径，默认 `outlines/draft.json` |

**返回**（JSON 字符串）：

```json
{
  "ok": true,
  "path": "outlines/draft.json",
  "slides_count": 8,
  "preview": [{ "pageTitle": "...", "itemCount": 3, "hasImages": false }]
}
```

**错误码**：`invalid_json`、`validation_error`、`write_failed`、`model_unavailable`。

### 4.2 `generate_ppt`

| 参数 | 说明 |
|------|------|
| `outline` | 大纲 JSON 字符串（与 `outline_path` 二选一） |
| `outline_path` | 沙箱内大纲文件路径 |
| `output_path` | 默认 `output/presentation.pptx` |
| `layout_mode` | `hybrid`（默认）或 `rule` |

**返回**：

```json
{
  "ok": true,
  "output_path": "output/presentation.pptx",
  "pages": [
    {
      "pageTitle": "我们的三大核心优势",
      "selectedLayout": "三列并列-等宽横排",
      "layoutIndex": 12,
      "selectionMethod": "ai",
      "reason": "三个并列要点，每点有标题和正文"
    }
  ],
  "warnings": []
}
```

**错误码**：`outline_invalid`、`template_missing`、`layout_not_found`、`image_load_failed`、`write_failed`。

---

## 5. Hybrid 选版与规则兜底

### 5.1 流程

1. 始终计算 `rule_layout = select_layout_by_rule(slide_spec, layout_index)`。
2. `layout_mode == "rule"` → 使用 `rule_layout`，`selectionMethod=rule`。
3. `layout_mode == "hybrid"` 且 `ctx.chat_model` 可用：
   - 构造 prompt（`slide` + `availableLayouts` 摘要，移植参考 `layout_selection_prompt`）。
   - 模型返回 JSON：`selectedLayoutName`、`confidence`、`reason`。
   - 若 `selectedLayoutName` 存在于索引且 `confidence >= 0.65` → 采用，`selectionMethod=ai`。
   - 否则 → `rule_layout`，`selectionMethod=rule_fallback`。
4. 模型调用异常 → 同 rule_fallback。

### 5.2 规则映射（与参考一致）

| 内容信号 | 优先 Layout |
|----------|-------------|
| 3 个普通要点 | 三列并列-等宽横排 |
| 4 个要点 | 四宫格-田字分布 |
| 6 个要点 | 要点列表-双列六条 |
| 2 个要点 | 二列对比-左右等分 |
| 3 个指标 | 大数字展示-三项居中 |
| 4 个指标 | 大数字展示-横向四项 |
| 1–6 张图 | 左图右文 / 两图并排 / … / 六图宫格 |
| 单段长正文 | 单段叙述-通栏正文 |
| 单条短观点 | 引言金句-居中 |
| 封面 | 标题幻灯片 |

`find_first_layout` 按名称列表 + `contentSignals.layoutType` 回退，避免硬编码单一名称失效。

### 5.3 常量

- `AI_MIN_CONFIDENCE = 0.65`（模块常量；若后续改为 Settings 环境变量，须同步 `backend/.env.example` 与 `backend/.env.dev`）。

---

## 6. 填充与图片

### 6.1 文本

- 自 `layout_index.json` 构建 `layoutIndex → { ph.idx → label }`，并与 `Presentation` 运行时 placeholder 合并。
- `value_for_label(slide_spec, label)` 覆盖 title/body/left_*/right_*/col*/grid*/item*/metric*（移植参考脚本）。
- 跳过 `PP_PLACEHOLDER.PICTURE` 的文本赋值。
- 生成前删除模板内已有幻灯片，仅保留 slide layouts。

### 6.2 图片

- `images[].path` 仅沙箱相对路径；经 `AgentFileSandbox` 解析读文件。
- 按 layout 中 picture placeholder **出现顺序** 与 `images[]` 对齐；`caption` 写入说明类 label。
- 支持 png/jpg/jpeg/webp；单张失败 → `image_load_failed`，不自动改选版。

### 6.3 已知模板限制

参考文档：部分 Layout 含非占位符装饰形状（如「三列并列-上标题下正文」「2_大数字展示-横向四项」），仅填充 placeholder，装饰形状保持模板默认。

---

## 7. SKILL.md 与 Planner 路由

### 7.1 子 Agent 流程

1. 无现成大纲 → `draft_ppt_outline` → 可选 `read_file` 给用户确认 → `generate_ppt`。
2. 已有 JSON/文件 → 直接 `generate_ppt`。
3. 图片须已在沙箱（用户上传或 `file` skill 写入）后再生成。
4. 完成后返回 `output_path` 与 `pages` 摘要。

### 7.2 Planner 路由触发词（示例）

- 做 PPT、生成 PPT、制作幻灯片、生成 pptx、导出演示文稿
- 把大纲做成 PPT、根据大纲生成幻灯片
- create presentation、generate slides

### 7.3 INDEX.md 条目

```markdown
- `ppt`：你是 PPT 制作助手。根据结构化大纲或用户描述生成 .pptx；须调用 draft_ppt_outline / generate_ppt，禁止编造文件路径或版式结果。
```

---

## 8. 测试与维护

### 8.1 测试

| 类型 | 内容 |
|------|------|
| 单元 | `normalize_slide` 各输入形态；`select_layout_by_rule` 对照参考 `test_outline.json` 期望 layout 名 |
| 集成 | `layout_mode=rule` 端到端生成 pptx（无 LLM）；断言文件存在、页数、占位符非空 |
| 可选 | hybrid 用 mock `chat_model` 返回固定 JSON |

### 8.2 版式库维护

```bash
cd backend
python -m app.agent.skills.ppt.pptmaker.extract_layout_index \
  app/agent/skills/ppt/assets/template.pptx \
  app/agent/skills/ppt/assets/layout_index.json
```

更新 `template.pptx` 后必须重建 `layout_index.json` 并提交仓库。

### 8.3 实现前资产迁移

将桌面参考目录中以下文件复制到 skill `assets/`（文件名可英文化）：

- `标准layout_P0P1版式库.pptx` → `template.pptx`
- `标准layout_P0P1版式库_layout_index.json` → `layout_index.json`

---

## 9. 实现清单（供 writing-plans 拆分）

1. `pyproject.toml` 添加 `python-pptx`。
2. 扩展 `SkillToolContext` + `executor_node` 注入 `chat_model`。
3. 迁移 `pptmaker/*` 核心逻辑（normalize、layout_select、fill、generate）。
4. 复制 assets；实现 `extract_layout_index` 模块入口。
5. `ppt/tools.py` + `ppt/SKILL.md` + `INDEX.md` 注册。
6. 测试与文档回填（实现完成后更新本文 **状态** 为已实现）。

---

## 10. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 输入形态 | 自然语言 + 结构化 JSON | 用户确认「两者都要」 |
| 工具形态 | 双工具流水线 | 大纲可预览/编辑，职责清晰 |
| 选版策略 | Hybrid + 规则兜底 | 对齐参考实现，兼顾语义与稳定 |
| 选版模型 | 当前 run Chat 模型 | 避免 duplicate API 配置 |
| 图片 | 完整支持 | 用户确认 |
| 模板位置 | skill 内置 assets | 用户确认 |
| 自定义模板 | 非目标 v1 | YAGNI |
