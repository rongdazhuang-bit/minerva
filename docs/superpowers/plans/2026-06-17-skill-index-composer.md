# Skill INDEX.json 与对话框 `/` 技能选择实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Agent 技能注册表迁移为 `INDEX.json`（含 `composer_visible`），并在对话输入框支持 `/` 技能选择与 `preferred_skills` 确定性单步 Plan。

**Architecture:** `skill_loader` 解析 JSON 注册表并扩展 `IndexedSkill`；`planner_node` 在单 skill `preferred_skills` 时跳过 LLM；前端通过 `GET /agent/v2/skills` 驱动 `/` 浮层，发送时 strip 前缀并传 `preferred_skills`。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, pytest；React 18, TypeScript, Ant Design, TanStack Query

**Spec:** `docs/superpowers/specs/2026-06-17-skill-index-composer-design.md`

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| Create | `backend/app/agent/skills/INDEX.json` | 技能注册表（替代 INDEX.md） |
| Delete | `backend/app/agent/skills/INDEX.md` | 移除 markdown 注册表 |
| Modify | `backend/app/agent/infrastructure/skill_loader.py` | JSON 解析、`composer_visible` |
| Modify | `backend/app/agent/api/v2/schemas.py` | `AgentSkillItemOut.composer_visible` |
| Modify | `backend/app/agent/api/v2/router.py` | API 映射新字段 |
| Modify | `backend/app/agent/graphs/nodes/planner.py` | 确定性单步 Plan |
| Modify | `backend/app/agent/service/skill_files_service.py` | INDEX.json 路径与 registry |
| Modify | `backend/app/agent/api/v2/skills_mgmt_router.py` | INDEX.json 白名单 |
| Modify | `backend/app/agent/domain/plan.py` | docstring INDEX.json |
| Create | `backend/tests/test_skill_index_json.py` | INDEX.json 解析单测 |
| Create | `backend/tests/test_planner_preferred_skill.py` | 强制单步 Plan 单测 |
| Modify | `frontend/src/api/agent.ts` | `composer_visible` 类型 |
| Modify | `frontend/src/features/agent/agentSkillUi.ts` | 前缀解析 helper |
| Create | `frontend/src/features/agent/AgentSkillSlashMenu.tsx` | `/` 浮层组件 |
| Modify | `frontend/src/features/agent/AgentsPage.tsx` | 接入菜单与 preferred_skills |
| Modify | `frontend/src/features/agent/AgentsPage.css` | 浮层样式 |
| Modify | `frontend/src/features/agent/skills/AgentSkillRegistryPage.tsx` | 编辑 INDEX.json |
| Modify | `frontend/src/features/agent/skills/AgentSkillsListPage.tsx` | 文案 |
| Modify | `docs/superpowers/specs/2026-06-17-skill-index-composer-design.md` | 状态 → 已实现 |

---

### Task 1: INDEX.json 迁移文件

**Files:**
- Create: `backend/app/agent/skills/INDEX.json`
- Delete: `backend/app/agent/skills/INDEX.md`

- [ ] **Step 1: 创建 INDEX.json**

将现有 7 条 skill 写入（顺序与现 INDEX.md 一致，全部 `composer_visible: true`）：

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
      "id": "district",
      "description": "你是行政区域查询助手。按地名或关键词查询 adcode 与区划层级，须调用 search_district_tool，禁止编造区划。",
      "composer_visible": true
    },
    {
      "id": "ip_location",
      "description": "你是 IP 定位助手。查询 IP 所在省市与 adcode，须调用 lookup_ip_location，禁止编造位置。",
      "composer_visible": true
    },
    {
      "id": "datetime",
      "description": "你是日期时间助手。涉及当前日期、时刻、星期时，须先调用 get_system_datetime，禁止编造实时时间。",
      "composer_visible": true
    },
    {
      "id": "file",
      "description": "你是工作区文件助手。可在沙箱内列出目录、读取/写入文本、创建目录与文件、删除及移动/重命名；路径均为沙箱内相对路径，须调用工具完成，禁止编造。",
      "composer_visible": true
    },
    {
      "id": "ppt",
      "description": "你是 **PPT / 演示文稿生成助手**（`skill_id=ppt`）。当用户要**生成新的 `.pptx` 幻灯片文件**时必须选本 skill——包括：做 PPT、生成演示文稿/幻灯片/pptx、把 PDF/Word/大纲/报告转成 PPT、按 pptx 模板填充、高视觉自由设计等；支持 `layout_fill`（默认）/`template_fill`/`svg_design` 三引擎。仅读写沙箱已有文件而不生成 deck 时选 `file`；仅闲聊选 `general`。须调用 ingest / draft_ppt_outline / generate_ppt 等工具，禁止编造 output_path 或版式结果。",
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

- [ ] **Step 2: 删除 INDEX.md**

```bash
git rm backend/app/agent/skills/INDEX.md
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/skills/INDEX.json
git commit -m "feat(agent): migrate skill registry from INDEX.md to INDEX.json"
```

---

### Task 2: skill_loader JSON 解析（TDD）

**Files:**
- Create: `backend/tests/test_skill_index_json.py`
- Modify: `backend/app/agent/infrastructure/skill_loader.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for INDEX.json skill registry parsing."""

from __future__ import annotations

import json

import pytest

from app.agent.infrastructure import skill_loader as sl


@pytest.fixture(autouse=True)
def _clear_skill_cache() -> None:
    sl.invalidate_skill_cache()
    yield
    sl.invalidate_skill_cache()


def test_parse_index_skills_reads_composer_visible() -> None:
    data = {
        "version": 1,
        "skills": [
            {"id": "weather", "description": "天气", "composer_visible": False},
            {"id": "general", "description": "通用"},
        ],
    }
    entries = sl.parse_index_skills(data)
    assert len(entries) == 2
    assert entries[0].id == "weather"
    assert entries[0].composer_visible is False
    assert entries[1].composer_visible is True


def test_parse_index_skills_skips_missing_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sl, "_SKILLS_ROOT", tmp_path)
    (tmp_path / "weather").mkdir()
    (tmp_path / "weather" / "SKILL.md").write_text("# w", encoding="utf-8")
    data = {
        "version": 1,
        "skills": [
            {"id": "weather", "description": "ok"},
            {"id": "ghost", "description": "missing dir"},
        ],
    }
    entries = sl.parse_index_skills(data)
    assert [e.id for e in entries] == ["weather"]


def test_list_composer_visible_skills_filters_hidden() -> None:
    visible = sl.list_composer_visible_skills()
    ids = [s.id for s in visible]
    assert "weather" in ids
    assert all(s.composer_visible for s in visible)


def test_list_indexed_skills_includes_all_registered() -> None:
    all_skills = sl.list_indexed_skills()
    assert len(all_skills) >= 7
    assert any(s.id == "weather" and not s.composer_visible is None for s in all_skills)
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd backend
pytest tests/test_skill_index_json.py -v
```

Expected: FAIL — `parse_index_skills` / `list_composer_visible_skills` 未定义

- [ ] **Step 3: 实现 skill_loader 变更**

在 `skill_loader.py` 中：

1. 模块 docstring 与 `_INDEX_FILE = "INDEX.json"`
2. 删除 `_INDEX_ENTRY_RE`、`load_index_markdown`、`parse_index_skill_entries` 的 markdown 逻辑
3. 扩展 dataclass：

```python
@dataclass(frozen=True)
class IndexedSkill:
    """One row from ``skills/INDEX.json``."""

    id: str
    description: str
    composer_visible: bool = True
```

4. 新增函数：

```python
def load_index_json() -> dict[str, object] | None:
    """Read and parse ``skills/INDEX.json``; return None on missing/invalid file."""

    path = skills_root() / _INDEX_FILE
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("invalid INDEX.json at {}", path)
        return None
    if not isinstance(raw, dict):
        log.warning("INDEX.json root must be object")
        return None
    return raw


def parse_index_skills(data: dict[str, object] | None = None) -> list[IndexedSkill]:
    """Parse ``skills`` array from INDEX.json; fallback to directory discovery."""

    payload = data if data is not None else load_index_json()
    if not payload:
        return _discover_skills_from_directories()
    raw_skills = payload.get("skills")
    if not isinstance(raw_skills, list) or not raw_skills:
        return _discover_skills_from_directories()
    entries: list[IndexedSkill] = []
    root = skills_root()
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        sid = _normalize_skill_id(str(item.get("id", "")))
        desc = str(item.get("description", "")).strip()
        if not sid or not desc:
            continue
        if not (root / sid).is_dir():
            continue
        visible = item.get("composer_visible", True)
        composer_visible = visible if isinstance(visible, bool) else True
        entries.append(
            IndexedSkill(id=sid, description=desc, composer_visible=composer_visible)
        )
    if entries:
        return entries
    return _discover_skills_from_directories()
```

5. `_discover_skills_from_directories` 返回 `IndexedSkill(id=..., description=..., composer_visible=True)`

6. `list_indexed_skills` 改为 `return tuple(parse_index_skills())`

7. 新增：

```python
def list_composer_visible_skills() -> tuple[IndexedSkill, ...]:
    """Skills shown in the chat composer ``/`` menu."""

    return tuple(s for s in list_indexed_skills() if s.composer_visible)
```

8. 文件顶部增加 `import json`

- [ ] **Step 4: 运行测试确认 PASS**

```bash
cd backend
pytest tests/test_skill_index_json.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/tests/test_skill_index_json.py
git commit -m "feat(agent): parse skill registry from INDEX.json with composer_visible"
```

---

### Task 3: API 暴露 composer_visible

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`
- Modify: `backend/app/agent/domain/plan.py`

- [ ] **Step 1: 扩展 schema**

`schemas.py` 中 `AgentSkillItemOut`：

```python
class AgentSkillItemOut(BaseModel):
    """One built-in agent skill."""

    id: str
    description: str
    composer_visible: bool = True
```

- [ ] **Step 2: 更新 router 映射**

`router.py` `list_agent_skills`：

```python
    return AgentSkillListOut(
        skills=[
            AgentSkillItemOut(
                id=s.id,
                description=s.description,
                composer_visible=s.composer_visible,
            )
            for s in list_indexed_skills()
        ]
    )
```

docstring 中 `INDEX.md` → `INDEX.json`。

- [ ] **Step 3: plan.py docstring**

`_validate_skill_id_registered` docstring：`skills/INDEX.json`

- [ ] **Step 4: 手动验证 API**

```bash
cd backend
pytest tests/test_skill_index_json.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py backend/app/agent/domain/plan.py
git commit -m "feat(agent): expose composer_visible on GET /agent/v2/skills"
```

---

### Task 4: skills-mgmt 改用 INDEX.json

**Files:**
- Modify: `backend/app/agent/service/skill_files_service.py`
- Modify: `backend/app/agent/api/v2/skills_mgmt_router.py`

- [ ] **Step 1: skill_files_service 变更**

1. import 改为 `parse_index_skills, load_index_json`（移除 `parse_index_skill_entries`）
2. `write_text`：`path.name == "INDEX.json"` 时 `invalidate_skill_cache(None)`；删除 `INDEX.md` 分支
3. `list_registry`：

```python
    def list_registry(self) -> list[dict[str, object]]:
        """List indexed skills with id, description, and on-disk file counts."""

        data = load_index_json()
        if data and isinstance(data.get("skills"), list):
            entries = [
                entry
                for entry in parse_index_skills(data)
                if (self.root / entry.id).is_dir()
            ]
        else:
            entries = self._discover_local_skills()
        registry: list[dict[str, object]] = []
        for entry in entries:
            registry.append(
                {
                    "id": entry.id,
                    "description": entry.description,
                    "composer_visible": entry.composer_visible,
                    "file_count": self._count_skill_files(entry.id),
                }
            )
        return registry
```

4. `_discover_local_skills` 返回 `IndexedSkill(..., composer_visible=True)`
5. `_invalidate_after_delete`：`INDEX.json` 替换 `INDEX.md`

- [ ] **Step 2: skills_mgmt_router**

将所有 `INDEX.md` 字符串替换为 `INDEX.json`（约 line 51 路径校验）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/service/skill_files_service.py backend/app/agent/api/v2/skills_mgmt_router.py
git commit -m "feat(agent): skills-mgmt reads and invalidates INDEX.json registry"
```

---

### Task 5: Planner 确定性单步 Plan（TDD）

**Files:**
- Create: `backend/tests/test_planner_preferred_skill.py`
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Modify: `backend/app/agent/graphs/nodes/planner.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for preferred_skills forced single-step plan."""

from __future__ import annotations

from app.agent.infrastructure.skill_loader import plan_from_preferred_skill


def test_plan_from_preferred_skill_single_valid() -> None:
    plan = plan_from_preferred_skill(["weather"], "北京天气怎么样")
    assert plan is not None
    assert len(plan.steps) == 1
    assert plan.steps[0].skill_id == "weather"
    assert plan.steps[0].goal == "北京天气怎么样"


def test_plan_from_preferred_skill_empty_pref_returns_none() -> None:
    assert plan_from_preferred_skill([], "hello") is None


def test_plan_from_preferred_skill_multiple_returns_none() -> None:
    assert plan_from_preferred_skill(["weather", "file"], "x") is None


def test_plan_from_preferred_skill_unknown_id_returns_none() -> None:
    assert plan_from_preferred_skill(["not_a_real_skill"], "x") is None
```

- [ ] **Step 2: 运行确认 FAIL**

```bash
cd backend
pytest tests/test_planner_preferred_skill.py -v
```

- [ ] **Step 3: 在 skill_loader.py 新增 helper**

```python
def plan_from_preferred_skill(
    preferred_skills: list[str],
    user_text: str,
) -> "Plan | None":
    """When exactly one registered skill is preferred, build a single-step Plan without LLM."""

    from app.agent.domain.plan import Plan, PlanStep

    if len(preferred_skills) != 1:
        return None
    skill = get_indexed_skill(preferred_skills[0])
    if skill is None:
        return None
    goal = (user_text or "").strip() or skill.description
    return Plan(steps=[PlanStep(id="s1", skill_id=skill.id, goal=goal)])
```

- [ ] **Step 4: 修改 planner_node**

在 `planner_node` 中，`request_text = (user_text or "").strip()` 之后、`planner_messages = [...]` 之前插入：

```python
    forced = plan_from_preferred_skill(pref, request_text)
    if forced is not None:
        plan = apply_planner_skill_match(forced, request_text)
        plan.steps = plan.steps[: settings.agent_max_plan_steps]
        # 复用现有 plan 持久化 / SSE / finalize_run_node 块（提取为内部 helper 或 goto 合并路径）
        ...
        return {"plan": plan, "plan_id": plan_id, "current_step_index": 0}
```

**实现要点：**

- 强制路径仍调用 `begin_run_node` + `finalize_run_node`
- **不**调用 `begin_llm_call_to_db` / `invoke_planner_plan`
- 将 plan 持久化、SSE `plan_created`、`finalize_run_node` 逻辑与 LLM 成功路径共用（可提取 `_persist_plan_and_emit(deps, plan, plan_node_id) -> tuple[Plan, uuid.UUID]` 减少重复）

- [ ] **Step 5: 运行测试 PASS**

```bash
cd backend
pytest tests/test_planner_preferred_skill.py tests/test_skill_index_json.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/app/agent/graphs/nodes/planner.py backend/tests/test_planner_preferred_skill.py
git commit -m "feat(agent): skip planner LLM when preferred_skills has one skill"
```

---

### Task 6: 前端 API 类型与 skills 查询

**Files:**
- Modify: `frontend/src/api/agent.ts`

- [ ] **Step 1: 扩展类型**

```typescript
export type AgentSkillListItem = {
  id: string
  description: string
  composer_visible?: boolean
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/agent.ts
git commit -m "feat(agent-ui): add composer_visible to AgentSkillListItem"
```

---

### Task 7: agentSkillUi 前缀解析 helper

**Files:**
- Modify: `frontend/src/features/agent/agentSkillUi.ts`

- [ ] **Step 1: 新增函数**

在 `stripSkillPrefixFromDraft` 附近添加：

```typescript
/** Parse leading ``/skill_id`` when id is in ``knownSkillIds`` (case-insensitive). */
export function parseSkillPrefixFromDraft(
  draft: string,
  knownSkillIds: readonly string[],
): string | null {
  const m = draft.match(/^\/([a-z][a-z0-9_]*)(\s|$)/i)
  if (!m) return null
  const id = m[1].toLowerCase()
  const known = new Set(knownSkillIds.map((s) => s.toLowerCase()))
  return known.has(id) ? id : null
}

/** Filter skills eligible for the composer slash menu. */
export function composerVisibleSkills(
  skills: { id: string; composer_visible?: boolean }[],
): { id: string; description: string }[] {
  return skills
    .filter((s) => s.composer_visible !== false)
    .map((s) => ({ id: s.id, description: (s as { description?: string }).description ?? s.id }))
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/agent/agentSkillUi.ts
git commit -m "feat(agent-ui): add skill prefix parsing helpers for composer"
```

---

### Task 8: AgentSkillSlashMenu 组件

**Files:**
- Create: `frontend/src/features/agent/AgentSkillSlashMenu.tsx`
- Modify: `frontend/src/features/agent/AgentsPage.css`

- [ ] **Step 1: 创建浮层组件**

```tsx
/**
 * Slash-command menu for picking an agent skill in the composer.
 */
import { useEffect, useMemo, useRef } from 'react'

export type AgentSkillSlashOption = {
  id: string
  description: string
}

type Props = {
  open: boolean
  options: AgentSkillSlashOption[]
  filter: string
  activeIndex: number
  onPick: (skillId: string) => void
  onHoverIndex: (index: number) => void
}

/** Filtered skill list shown above the composer when user types ``/``. */
export function AgentSkillSlashMenu({
  open,
  options,
  filter,
  activeIndex,
  onPick,
  onHoverIndex,
}: Props) {
  const listRef = useRef<HTMLUListElement | null>(null)

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return options
    return options.filter(
      (o) => o.id.toLowerCase().includes(q) || o.description.toLowerCase().includes(q),
    )
  }, [options, filter])

  useEffect(() => {
    if (!open || !listRef.current) return
    const el = listRef.current.children[activeIndex] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex, open])

  if (!open || filtered.length === 0) return null

  return (
    <ul ref={listRef} className="agents-page__skill-slash-menu" role="listbox">
      {filtered.map((opt, idx) => (
        <li
          key={opt.id}
          role="option"
          aria-selected={idx === activeIndex}
          className={
            idx === activeIndex
              ? 'agents-page__skill-slash-item agents-page__skill-slash-item--active'
              : 'agents-page__skill-slash-item'
          }
          onMouseDown={(e) => e.preventDefault()}
          onMouseEnter={() => onHoverIndex(idx)}
          onClick={() => onPick(opt.id)}
        >
          <span className="agents-page__skill-slash-id">/{opt.id}</span>
          <span className="agents-page__skill-slash-desc">{opt.description}</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 2: CSS**

在 `AgentsPage.css` 追加：

```css
.agents-page__composer {
  position: relative;
}

.agents-page__skill-slash-menu {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 100%;
  margin: 0 0 6px;
  padding: 4px 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--minerva-border, #2d3f55);
  border-radius: 10px;
  background: var(--minerva-surface, #1b2838);
  z-index: 20;
}

.agents-page__skill-slash-item {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
}

.agents-page__skill-slash-item--active,
.agents-page__skill-slash-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.agents-page__skill-slash-id {
  flex-shrink: 0;
  font-family: ui-monospace, monospace;
  color: var(--minerva-accent, #6eb6ff);
}

.agents-page__skill-slash-desc {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.85;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/agent/AgentSkillSlashMenu.tsx frontend/src/features/agent/AgentsPage.css
git commit -m "feat(agent-ui): add slash menu component for skill selection"
```

---

### Task 9: AgentsPage 集成 `/` 菜单与 preferred_skills

**Files:**
- Modify: `frontend/src/features/agent/AgentsPage.tsx`

- [ ] **Step 1: 加载 skills 列表**

```typescript
import { listAgentSkills } from '@/api/agent'
import { AgentSkillSlashMenu } from '@/features/agent/AgentSkillSlashMenu'
import {
  buildDisplayUserMessage,
  composerVisibleSkills,
  parseSkillPrefixFromDraft,
  stripSkillPrefixFromDraft,
  // ...existing imports
} from '@/features/agent/agentSkillUi'
```

在组件内：

```typescript
  const skillsQuery = useQuery({
    queryKey: ['agent-skills', workspaceId],
    queryFn: () => listAgentSkills(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const slashOptions = useMemo(
    () => composerVisibleSkills(skillsQuery.data?.skills ?? []),
    [skillsQuery.data?.skills],
  )

  const allSkillIds = useMemo(
    () => (skillsQuery.data?.skills ?? []).map((s) => s.id),
    [skillsQuery.data?.skills],
  )

  const [slashOpen, setSlashOpen] = useState(false)
  const [slashFilter, setSlashFilter] = useState('')
  const [slashActiveIndex, setSlashActiveIndex] = useState(0)
```

- [ ] **Step 2: draft onChange 检测 `/`**

```typescript
  const handleDraftChange = useCallback(
    (value: string) => {
      setDraft(value)
      const m = value.match(/^\/([a-z0-9_]*)$/i)
      if (m) {
        setSlashOpen(true)
        setSlashFilter(m[1] ?? '')
        setSlashActiveIndex(0)
      } else {
        setSlashOpen(false)
        setSlashFilter('')
      }
    },
    [],
  )

  const pickSlashSkill = useCallback((skillId: string) => {
    setDraft(`/${skillId} `)
    setSlashOpen(false)
    setSlashFilter('')
    setSlashActiveIndex(0)
    draftInputRef.current?.focus({ preventScroll: true })
  }, [])
```

- [ ] **Step 3: TextArea 键盘处理**

在 `onKeyDown`（新增）中：

```typescript
              onKeyDown={(e) => {
                if (!slashOpen) return
                const filtered = slashFilter
                  ? slashOptions.filter(/* same filter as menu */)
                  : slashOptions
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setSlashActiveIndex((i) => Math.min(i + 1, filtered.length - 1))
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setSlashActiveIndex((i) => Math.max(i - 1, 0))
                } else if (e.key === 'Enter' && !e.shiftKey && filtered.length > 0) {
                  e.preventDefault()
                  pickSlashSkill(filtered[slashActiveIndex]?.id ?? filtered[0].id)
                } else if (e.key === 'Escape') {
                  setSlashOpen(false)
                } else if (e.key === 'Tab' && filtered.length > 0) {
                  e.preventDefault()
                  pickSlashSkill(filtered[slashActiveIndex]?.id ?? filtered[0].id)
                }
              }}
```

`onChange` 改为 `handleDraftChange`。

- [ ] **Step 4: 渲染 AgentSkillSlashMenu**

在 `agents-page__composer` 内、`Input.TextArea` 之前：

```tsx
            <AgentSkillSlashMenu
              open={slashOpen && !streaming}
              options={slashOptions}
              filter={slashFilter}
              activeIndex={slashActiveIndex}
              onPick={pickSlashSkill}
              onHoverIndex={setSlashActiveIndex}
            />
```

- [ ] **Step 5: 修改 runAgentTurn / onSend**

`runAgentTurn` 增加可选 `preferredSkills` 参数；`onSend` 中：

```typescript
    const skillId = parseSkillPrefixFromDraft(draft, allSkillIds)
    const apiBody = stripSkillPrefixFromDraft(draft, skillId)
    if (!apiBody.trim() && !skillId) return
    const display = buildDisplayUserMessage(apiBody, skillId)
    // 新消息气泡 content = display
    // streamAgentRun preferred_skills: skillId ? [skillId] : []
```

在 `runAgentTurn` 新建用户消息处使用 `display` 而非 `apiBody`；`streamAgentRun` 传入 `preferred_skills`。

发送成功后 `setDraft('')` 并 `setSlashOpen(false)`。

- [ ] **Step 6: 手动验证**

1. 打开 `/app/agents`，输入 `/` 见 skill 列表
2. 选 `weather`，输入正文，发送
3. 网络面板确认 `preferred_skills: ["weather"]`，`user_message` 无 `/weather` 前缀

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/agent/AgentsPage.tsx
git commit -m "feat(agent-ui): wire slash menu and preferred_skills on send"
```

---

### Task 10: 技能管理页 INDEX.json

**Files:**
- Modify: `frontend/src/features/agent/skills/AgentSkillRegistryPage.tsx`
- Modify: `frontend/src/features/agent/skills/AgentSkillsListPage.tsx`

- [ ] **Step 1: AgentSkillRegistryPage**

- `INDEX_PATH = 'INDEX.json'`
- 页面标题与注释中的 `INDEX.md` → `INDEX.json`

- [ ] **Step 2: AgentSkillsListPage 文案**

注册表入口文案改为 `技能注册表 (INDEX.json)`。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/agent/skills/AgentSkillRegistryPage.tsx frontend/src/features/agent/skills/AgentSkillsListPage.tsx
git commit -m "feat(agent-ui): edit INDEX.json in skill registry page"
```

---

### Task 11: 文档与全量测试

**Files:**
- Modify: `docs/superpowers/specs/2026-06-17-skill-index-composer-design.md`

- [ ] **Step 1: 更新 spec 状态**

将 header `状态` 改为「已实现」，追加实现日期。

- [ ] **Step 2: 运行后端测试**

```bash
cd backend
pytest tests/test_skill_index_json.py tests/test_planner_preferred_skill.py tests/test_planner_llm.py -v
```

Expected: 全部 PASS

- [ ] **Step 3: 前端类型检查**

```bash
cd frontend
npm run build
```

Expected: 无 TypeScript 错误

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-17-skill-index-composer-design.md
git commit -m "docs(agent): mark skill INDEX.json composer design as implemented"
```

---

## Spec 覆盖自检

| Spec 要求 | 对应 Task |
|-----------|-----------|
| INDEX.json 替代 INDEX.md | Task 1, 2 |
| composer_visible 字段 | Task 2, 3, 4 |
| Agent 使用全部 skill | Task 2（list_indexed_skills 不过滤） |
| `/` 菜单仅可见 skill | Task 7, 8, 9 |
| preferred_skills + strip 前缀 | Task 9 |
| 单 skill 跳过 Planner LLM | Task 5 |
| skills-mgmt INDEX.json | Task 4, 10 |
| 测试 | Task 2, 5, 11 |

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-06-17-skill-index-composer.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做 review，迭代更快

**2. Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行并在检查点暂停

你想用哪种方式？
