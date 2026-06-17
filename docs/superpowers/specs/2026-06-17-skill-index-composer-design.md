# Skill 注册表 INDEX.json 与对话框 `/` 技能选择设计说明

**日期**：2026-06-17  
**状态**：已批准，待实现  
**范围**：将 Agent 内置技能注册表由 `INDEX.md` 迁移为 `INDEX.json`；在智能体对话输入框支持 `/` 触发技能提示与选择；通过 `preferred_skills` 与确定性单步 Plan 实现「选中即直接调用该 skill」。`composer_visible` 仅控制对话框菜单可见性，不影响 Agent / Planner 对全部已注册 skill 的使用。

**关系**：扩展 `docs/superpowers/specs/2026-05-27-agent-skills-management-design.md`（skills-mgmt 文件编辑、`skill_loader` 缓存失效）；复用 `frontend/src/features/agent/agentSkillUi.ts` 已有前缀工具函数；与 `GET /agent/v2/skills`、`planner_node`、`preferred_skills` 协同。

---

## 1. 目标与成功标准

### 1.1 目标

- 用 **`backend/app/agent/skills/INDEX.json`** 替代 **`INDEX.md`**，作为技能注册表唯一来源（顺序 = Planner 路由优先级）。
- 每条 skill 元数据包含：`id`、`description`、`composer_visible`（是否在对话框 `/` 菜单中展示）。
- 对话输入框：用户输入 `/` 时弹出可选 skill 列表（仅 `composer_visible !== false`）；选中后在输入框插入 `/skill_id ` 前缀。
- 发送消息时：气泡显示带前缀的完整文本；API `user_message` 为去掉前缀后的正文；`preferred_skills` 为 `[skill_id]`。
- 当 `preferred_skills` 恰为 1 个合法 skill 时，**跳过 Planner LLM**，直接生成单步 Plan，确保 Agent 直接调用该 skill。
- skills-mgmt 注册表编辑页改为编辑 `INDEX.json`（Monaco JSON 模式）。

### 1.2 成功标准

- `skill_loader.list_indexed_skills()` 从 `INDEX.json` 读取全部 skill；`composer_visible: false` 的 skill 仍参与 Planner 路由与子 Agent 编译。
- 编辑 `INDEX.json` 保存后，`GET /agent/v2/skills` 与 `/` 菜单在下次请求时反映新顺序、描述与可见性。
- 用户在对话框选 `/weather` 并发送「北京天气」→ 请求体 `user_message="北京天气"`、`preferred_skills=["weather"]`；Run 产生单步 Plan 且 `skill_id=weather`，不调用 Planner LLM。
- 未选 skill 时行为与现网一致（Planner LLM 路由）。
- `composer_visible: false` 的 skill 不出现在 `/` 菜单，但 Agent 仍可通过 Planner 自动路由或手动在 INDEX 中配置后由 LLM 选用。

### 1.3 非目标（本期）

- 多 skill 组合选择（`/weather` + `/file` 等）
- 工作区级 skill 注册表
- INDEX.json JSON Schema 在线校验 UI（仅 Monaco 语法高亮）
- 自动从 INDEX.md 运行时双读兼容（迁移完成后删除 INDEX.md）
- 修改各 skill 的 `SKILL.md` 结构或工具注册方式

---

## 2. 方案选型

### 2.1 注册表格式

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 单一 INDEX.json** | 有序 `skills` 数组，字段集中 | **采用** |
| B. 分散到 SKILL.md frontmatter | 可见性与顺序难统一管理 | 否决 |
| C. DB 镜像 | 与现 filesystem skills-mgmt 不一致 | 否决 |

### 2.2 选中 skill 后的调用语义

| 方案 | 说明 | 结论 |
|------|------|------|
| A. 仅增强 Planner 提示 | `preferred_skills` + 系统提示 | 不够可靠 |
| **B. 确定性单步 Plan** | 单 skill 时跳过 Planner LLM | **采用** |
| C. 完全绕过 Plan 图 | 直连 subagent | 改动面大，轨迹不一致 |

### 2.3 对话框交互

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 输入框前缀 + preferred_skills** | 与 `agentSkillUi.ts` 一致 | **采用** |
| B. 仅 API 偏好，无前缀 | 用户不可见已选 skill | 否决 |
| C. 纯文本前缀，后端解析 | 与现有 `preferred_skills` 重复 | 否决 |

---

## 3. INDEX.json 规范

### 3.1 文件路径

`backend/app/agent/skills/INDEX.json`

### 3.2 Schema（逻辑结构）

```json
{
  "version": 1,
  "skills": [
    {
      "id": "weather",
      "description": "你是天气查询助手。须先通过 IP 或行政区定位取得 adcode，再调用 get_weather_info（默认含实况与预报），禁止编造天气。",
      "composer_visible": true
    },
    {
      "id": "general",
      "description": "你是通用对话助手。根据用户目标给出清晰、准确的中文回答。",
      "composer_visible": true
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | int | 是 | 固定为 `1`，便于将来扩展 |
| `skills` | array | 是 | 有序列表；顺序 = Planner 匹配优先级 |
| `skills[].id` | string | 是 | 小写 `[a-z][a-z0-9_]*`，对应 `skills/<id>/` 目录名 |
| `skills[].description` | string | 是 | 子 Agent 系统提示首段 / Planner schema 描述 |
| `skills[].composer_visible` | boolean | 否 | 默认 `true`；`false` 时不出现在对话框 `/` 菜单 |

### 3.3 解析与 fallback

1. 若 `INDEX.json` 存在且可解析 → 使用其中 `skills` 数组（跳过 `id` 对应目录不存在的条目，与现 skills-mgmt `list_registry` 行为一致）。
2. 若文件缺失、JSON 无效或 `skills` 为空 → log warning，fallback 到 `_discover_skills_from_directories()`（含 `SKILL.md` 的子目录，按名称排序）；fallback 条目 `composer_visible=True`，`description=id`。
3. 不再读取 `INDEX.md`。

### 3.4 初始迁移

将现有 `INDEX.md` 中 7 条 skill 转为 `INDEX.json`；全部默认 `composer_visible: true`（后续可在管理页按需改为 `false`）。提交中删除 `INDEX.md`。

---

## 4. 后端设计

### 4.1 `skill_loader.py`

**数据结构：**

```python
@dataclass(frozen=True)
class IndexedSkill:
    id: str
    description: str
    composer_visible: bool = True
```

**主要变更：**

- `_INDEX_FILE = "INDEX.json"`
- 新增 `load_index_json() -> dict | None`
- 新增 `parse_index_skills(data: dict | None = None) -> list[IndexedSkill]`，替代 `parse_index_skill_entries` 对 markdown 的解析
- 保留 `list_indexed_skills()`、`get_indexed_skill()` 等对外 API；内部数据源改为 JSON
- 可选便捷函数 `list_composer_visible_skills() -> tuple[IndexedSkill, ...]`（过滤 `composer_visible`）

**文档字符串 / 注释：** 所有提及 `INDEX.md` 的 docstring 改为 `INDEX.json`。

### 4.2 `GET /agent/v2/skills`

**响应扩展（`AgentSkillItemOut`）：**

```python
class AgentSkillItemOut(BaseModel):
    id: str
    description: str
    composer_visible: bool = True
```

仍返回 **全部** 已注册 skill；前端根据 `composer_visible` 过滤 `/` 菜单。不在 API 层拆分 `for=composer` 端点，避免双份列表逻辑。

### 4.3 `planner_node` 确定性单步 Plan

在调用 `invoke_planner_plan` **之前**：

```python
pref = state.get("preferred_skills") or []
if len(pref) == 1:
    skill = get_indexed_skill(pref[0])
    if skill is not None:
        plan = Plan(steps=[PlanStep(
            id="s1",
            skill_id=skill.id,
            goal=(user_text or "").strip() or skill.description,
        )])
        # 持久化 plan、emit SSE、return state 更新（与 LLM 路径后续一致）
        ...
```

- `user_text` 为已去前缀的 `user_message`（前端负责 strip；后端不重复解析 `/` 前缀）。
- 若 `preferred_skills` 长度为 0 或 >1，或 id 不在 INDEX 中 → 走现有 Planner LLM 流程。
- 确定性路径仍执行 `apply_planner_skill_match`（对单步同 skill 通常为 no-op）。
- 确定性路径仍写入 run node 生命周期（`begin_run_node` / `finish_run_node`），SSE 事件类型与 LLM 路径一致。

### 4.4 `skill_files_service` / `skills_mgmt_router`

- 路径白名单：`INDEX.json` 替代 `INDEX.md`（读、写、删除后的 `invalidate_skill_cache(None)`）。
- `list_registry()`：读 `INDEX.json` 而非 markdown。
- zip 上传、单文件路径校验中涉及 `INDEX.md` 的分支改为 `INDEX.json`。

### 4.5 缓存失效

写 `INDEX.json` 后调用 `invalidate_skill_cache(None)`（与现 INDEX.md 行为相同）。

---

## 5. 前端设计

### 5.1 API 类型（`frontend/src/api/agent.ts`）

```typescript
export type AgentSkillListItem = {
  id: string
  description: string
  composer_visible?: boolean
}
```

页面 mount 时 `listAgentSkills(workspaceId)` 缓存 skill 列表供 composer 使用。

### 5.2 `AgentsPage` 对话框 `/` 菜单

**触发条件：** 光标所在行，从行首或空白后到光标之间，匹配 `^/?$` 或 `^/[a-z0-9_]*$`（即刚输入 `/` 或正在输入 skill id 前缀）。

**菜单内容：** `skills.filter(s => s.composer_visible !== false)`，按 `id` 或描述模糊匹配当前 `/` 后已输入片段。

**交互：**

- ↑ / ↓：高亮选项
- Enter / Tab：确认，插入 `/skill_id `（含 trailing space），设置 `selectedSkillId`
- Esc：关闭菜单
- 继续输入非匹配字符或移动光标：关闭或更新过滤

**发送逻辑（新消息，非 regenerate）：**

```typescript
const skillId = selectedSkillId // 从 draft 解析或 state 同步
const body = stripSkillPrefixFromDraft(draft, skillId)
const display = buildDisplayUserMessage(body, skillId)
// 气泡 content = display
// API user_message = body
// preferred_skills = skillId ? [skillId] : []
```

**状态同步：** `draft` 变化时若前缀被用户删除或改为其他 skill id，更新 `selectedSkillId`；发送成功后清空 draft 与 `selectedSkillId`。

**边界：**

- 用户手动输入 `/hidden_skill`（`composer_visible: false`）：若 id 在完整 skill 列表中存在，仍解析为 `preferred_skills`（高级用法）；菜单不展示该项。
- 选中 skill 后正文为空：允许发送（goal  fallback 为 description 或空，由后端 Plan 处理）。

### 5.3 UI 组件

新增 `AgentSkillSlashMenu`（或内联于 `AgentsPage`）：Ant Design `Dropdown` / 自定义浮层列表，样式与 `agents-page__composer` 对齐。不引入新 npm 依赖。

### 5.4 技能管理页

- `AgentSkillRegistryPage`：`INDEX_PATH = 'INDEX.json'`
- `SkillFileEditor`：`language="json"`
- `AgentSkillsListPage`：文案「技能注册表 (INDEX.json)」

---

## 6. 数据流

```
INDEX.json
    → skill_loader.list_indexed_skills()     → Planner / 子 Agent（全部 skill）
    → GET /agent/v2/skills                   → 前端缓存
    → filter composer_visible                → / 菜单

用户选 /weather + 输入正文
    → POST run { user_message, preferred_skills: ['weather'] }
    → planner_node: 单步 Plan(skill_id=weather) [无 LLM]
    → subagent_runner → weather 工具
```

---

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| INDEX.json 格式错误 | log warning；fallback 目录发现；skills-mgmt 保存时可选返回 400（若做服务端校验） |
| preferred skill id 已不存在 | 发送前校验失败 → toast，清除无效前缀，不发送 |
| preferred_skills 含多个 id | 忽略确定性短路，走 Planner LLM（本期前端只传 0 或 1 个） |
| streaming 中 | 禁用 `/` 菜单与发送（与现 composer disabled 一致） |

---

## 8. 测试

### 8.1 后端

- `parse_index_skills`：正常 JSON、`composer_visible` 省略默认为 true、无效 JSON fallback
- `list_indexed_skills` 顺序与 INDEX 数组一致
- `planner_node`：`preferred_skills=['weather']` 时不 mock LLM 被调用，Plan 单步且 skill_id 正确
- `skill_files_service.list_registry` 读 INDEX.json
- 写 INDEX.json 后 `invalidate_skill_cache` 生效

### 8.2 前端

- `stripSkillPrefixFromDraft` / `buildDisplayUserMessage` 已有逻辑；补充与 composer 集成的单元测试（若项目惯例允许）
- 手动：/` 菜单过滤、`composer_visible: false` 不展示但手动前缀仍可发送

---

## 9. 实现顺序建议

1. 后端：`IndexedSkill` + INDEX.json 解析 + 迁移文件 + 更新 tests
2. 后端：`AgentSkillItemOut.composer_visible` + planner 确定性单步
3. 后端：skills-mgmt INDEX.json 路径
4. 前端：API 类型 + `listAgentSkills` 接入
5. 前端：`/` 菜单 + 发送 preferred_skills
6. 前端：注册表编辑页 INDEX.json

---

## 10. 文件清单（预期改动）

| 路径 | 变更 |
|------|------|
| `backend/app/agent/skills/INDEX.json` | 新增 |
| `backend/app/agent/skills/INDEX.md` | 删除 |
| `backend/app/agent/infrastructure/skill_loader.py` | JSON 解析、`composer_visible` |
| `backend/app/agent/api/v2/schemas.py` | `composer_visible` 字段 |
| `backend/app/agent/api/v2/router.py` | 映射新字段 |
| `backend/app/agent/graphs/nodes/planner.py` | 确定性单步 Plan |
| `backend/app/agent/service/skill_files_service.py` | INDEX.json 路径 |
| `backend/app/agent/api/v2/skills_mgmt_router.py` | INDEX.json 路径 |
| `frontend/src/api/agent.ts` | 类型扩展 |
| `frontend/src/features/agent/AgentsPage.tsx` | `/` 菜单、preferred_skills |
| `frontend/src/features/agent/agentSkillUi.ts` | 可选：从 draft 解析 skill id |
| `frontend/src/features/agent/skills/AgentSkillRegistryPage.tsx` | INDEX.json |
| `frontend/src/features/agent/skills/AgentSkillsListPage.tsx` | 文案 |
| `backend/tests/test_skill_*.py` | 更新 / 新增 |

---

**状态**：设计已于 2026-06-17 与产品方确认（对话框方案 A；`composer_visible` 默认 true；单 skill 跳过 Planner LLM）。
