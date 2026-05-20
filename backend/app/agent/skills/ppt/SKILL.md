# ppt（PPT Maker）

根据结构化大纲或自然语言描述，在**工作区沙箱**内生成 `.pptx` 演示文稿。版式来自内置 P0/P1 版式库（Hybrid 选版：LLM 优先，规则兜底）。

## 何时使用

**Planner 必选本 skill（`skill_id=ppt`）**：用户要制作、生成、导出 PPT/幻灯片/pptx，或把大纲做成演示文稿。

**子 Agent 执行**：必须通过工具完成，禁止编造 `output_path`、版式名称或选版结果。

### 推荐流程

1. **无现成大纲**：先 `draft_ppt_outline(brief)` → 大纲写入沙箱（默认 `outlines/draft.json`）→ 可向用户展示 preview → `generate_ppt(outline_path=...)`。
2. **已有大纲 JSON 或沙箱文件**：直接 `generate_ppt(outline_path=...)` 或 `generate_ppt(outline=...)`。
3. **配图**：图片须先存在于沙箱（用户上传或 `file` skill 写入）；大纲中 `images[].path` 为沙箱相对路径。
4. 完成后向用户报告 `output_path`（默认 `output/presentation.pptx`）及 `pages` 选版摘要。

## Planner 路由

- 做 PPT
- 生成 PPT
- 制作幻灯片
- 生成 pptx
- 导出演示文稿
- 把大纲做成 PPT
- 根据大纲生成幻灯片
- 制作演示文稿
- create presentation
- generate slides
- ppt maker

## 工具一览

| 工具 | 说明 |
|------|------|
| `draft_ppt_outline` | `brief` 必填；可选 `slide_count`、`output_path`（默认 `outlines/draft.json`）。返回 `path`、`slides_count`、`preview`。 |
| `generate_ppt` | `outline` 或 `outline_path` 二选一；`output_path` 默认 `output/presentation.pptx`；`layout_mode` 为 `hybrid`（默认）或 `rule`。返回 `pages`、`warnings`。 |

## 大纲 schema（摘要）

```json
{
  "meta": { "title": "封面主标题", "subtitle": "副标题" },
  "slides": [
    { "pageTitle": "页标题", "items": [{ "title": "a", "body": "b" }] },
    { "pageTitle": "指标", "keyNumbers": [{ "number": "19", "label": "名称", "desc": "说明" }] },
    { "pageTitle": "配图", "images": [{ "path": "images/a.png", "caption": "说明" }] }
  ]
}
```

## 错误码

`draft_ppt_outline`：`invalid_json`、`validation_error`、`write_failed`、`model_unavailable`

`generate_ppt`：`outline_invalid`、`template_missing`、`layout_not_found`、`image_load_failed`、`write_failed`

## 版式库维护（开发）

更新 `assets/template.pptx` 后须重建 `assets/layout_index.json`：

```bash
cd backend
python -m app.agent.skills.ppt.pptmaker.extract_layout_index \
  app/agent/skills/ppt/assets/template.pptx \
  app/agent/skills/ppt/assets/layout_index.json
```
