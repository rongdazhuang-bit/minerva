# Agent `system_datetime` 技能与工具链路 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 `system_datetime` 技能包、服务端 skill 解析（显式 / 自动）、tools 动态加载与最多 2 轮 LLM tool 循环，并提供 `GET /agent/skills` 与前端 `/` 动态选 skill。

**Architecture:** `INDEX.md` 为技能唯一索引；`skill_resolver` 产出 `effective_skill_ids`；`skill_tools` 用 `importlib` 从各子目录 `tools.py` 注册到 `ToolRegistry`；`AgentRunService` 在 `effective_skill_ids` 非空时向 `ChatService` 传 `tools` 并执行 tool 循环；前端通过 `listAgentSkills` 拉取菜单，显式选择时只传一个 `skill_id`，否则传空数组走自动匹配。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / pytest / React 19 / Ant Design / TanStack Query / i18next

**Spec:** `docs/superpowers/specs/2026-05-16-agent-system-datetime-skill-design.md`

**注释:** 新增 Python 类/公开函数、TS 导出函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring / JSDoc）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/agent/skills/INDEX.md` | 注册 `system_datetime` |
| `backend/app/agent/skills/system_datetime/SKILL.md` | 技能说明文档 |
| `backend/app/agent/skills/system_datetime/tools.py` | `get_system_datetime` 工具 |
| `backend/app/agent/infrastructure/skill_loader.py` | 解析 INDEX 描述、列出可展示 skill |
| `backend/app/agent/infrastructure/skill_resolver.py` | 显式 / 自动 `effective_skill_ids` |
| `backend/app/agent/infrastructure/skill_tools.py` | 动态加载 `tools.py` |
| `backend/app/agent/service/agent_run_service.py` | resolver + tools + 2-round loop |
| `backend/app/agent/api/schemas.py` | `AgentSkillListOut` |
| `backend/app/agent/api/router.py` | `GET .../agent/skills` |
| `minerva-ui/src/api/agent.ts` | `listAgentSkills` |
| `minerva-ui/src/features/workspace/AgentsPage.tsx` | `/` 菜单、发送拆分 |
| `backend/tests/test_skill_*.py`, `test_agent_run_tools.py` | 单测 |

**Note:** `skills/<id>/` 下无 `__init__.py`；`skill_tools` 须用 `importlib.util.spec_from_file_location` 加载 `tools.py`，勿假设 `app.agent.skills.<id>.tools` 包导入可用。

---

### Task 1: `system_datetime` 技能包 + INDEX

**Files:**
- Create: `backend/app/agent/skills/system_datetime/SKILL.md`
- Create: `backend/app/agent/skills/system_datetime/tools.py`
- Modify: `backend/app/agent/skills/INDEX.md`
- Test: `backend/tests/test_skill_loader.py`

- [ ] **Step 1: 更新 INDEX**

在 `backend/app/agent/skills/INDEX.md` 的「子技能列表」增加：

```markdown
- `system_datetime`：获取当前系统时间（UTC/本地）。
```

- [ ] **Step 2: 编写 SKILL.md**

`backend/app/agent/skills/system_datetime/SKILL.md` 简要说明：涉及当前日期、时刻、星期等问题时应调用 `get_system_datetime`，勿编造时间。

- [ ] **Step 3: 编写 tools.py**

```python
"""Executable tools for the ``system_datetime`` agent skill."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agent.infrastructure.tool_registry import ToolRegistry


async def _get_system_datetime(*, timezone: str = "UTC") -> str:
    """Return current server time as JSON (``iso``, ``timezone``, ``unix``)."""

    tz = (timezone or "UTC").strip().upper()
    if tz == "LOCAL":
        now = datetime.now().astimezone()
        tz_label = "local"
    else:
        now = datetime.now(timezone.utc)
        tz_label = "UTC"
    payload = {
        "iso": now.isoformat().replace("+00:00", "Z") if tz_label == "UTC" else now.isoformat(),
        "timezone": tz_label,
        "unix": int(now.timestamp()),
    }
    return json.dumps(payload, ensure_ascii=False)


def register(registry: ToolRegistry) -> None:
    """Register ``get_system_datetime`` on the shared registry."""

    registry.register(
        "get_system_datetime",
        _get_system_datetime,
        description="返回服务器当前日期时间（ISO-8601）。",
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "enum": ["UTC", "local"],
                    "description": "时区：UTC 或服务器本地。",
                }
            },
        },
    )
```

- [ ] **Step 4: 扩展 test_skill_loader**

在 `backend/tests/test_skill_loader.py` 增加：

```python
def test_parse_skill_ids_finds_system_datetime() -> None:
  text = skill_loader.load_index_text()
  ids = skill_loader.parse_skill_ids_from_index(text)
  assert "system_datetime" in ids


def test_load_skill_markdown_system_datetime() -> None:
  body = skill_loader.load_skill_markdown("system_datetime")
  assert len(body.strip()) > 0
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_skill_loader.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/skills backend/tests/test_skill_loader.py
git commit -m "feat(agent): add system_datetime skill pack"
```

---

### Task 2: `skill_loader` 描述解析 + 列表 API 数据

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Test: `backend/tests/test_skill_loader.py`

- [ ] **Step 1: 写失败测试**

```python
def test_parse_skill_descriptions_from_index() -> None:
    text = skill_loader.load_index_text()
    desc = skill_loader.parse_skill_descriptions_from_index(text)
    assert desc.get("system_datetime")
    assert "时间" in desc["system_datetime"] or "UTC" in desc["system_datetime"]


def test_list_indexed_skills_filters_missing_skill_md() -> None:
    items = skill_loader.list_indexed_skills()
    ids = [x["id"] for x in items]
    assert "system_datetime" in ids
    assert all(skill_loader.load_skill_markdown(i) for i in ids)  # SKILL.md exists
```

- [ ] **Step 2: Run → FAIL**

```bash
cd backend && pytest tests/test_skill_loader.py::test_parse_skill_descriptions_from_index -v
```

- [ ] **Step 3: 实现**

在 `skill_loader.py` 增加：

```python
def parse_skill_descriptions_from_index(index_text: str) -> dict[str, str]:
    """Parse ``- `id`：description`` bullets into a map."""

    out: dict[str, str] = {}
    for raw in index_text.splitlines():
        line = raw.strip()
        m = re.match(r"^[-*]\s+`?([a-z0-9_]+)`?\s*[：:]\s*(.+)$", line, re.I)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def list_indexed_skills() -> list[dict[str, str]]:
    """Return skills from INDEX that have an on-disk ``SKILL.md``."""

    index_text = load_index_text()
    ids = parse_skill_ids_from_index(index_text)
    desc_map = parse_skill_descriptions_from_index(index_text)
    items: list[dict[str, str]] = []
    for sid in ids:
        skill_md = _SKILLS_ROOT / sid / "SKILL.md"
        if not skill_md.is_file():
            continue
        items.append({"id": sid, "description": desc_map.get(sid) or sid})
    return items
```

- [ ] **Step 4: Run tests → PASS**

```bash
cd backend && pytest tests/test_skill_loader.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/tests/test_skill_loader.py
git commit -m "feat(agent): parse skill descriptions and list indexed skills"
```

---

### Task 3: `skill_resolver`（显式 / 自动）

**Files:**
- Create: `backend/app/agent/infrastructure/skill_resolver.py`
- Test: `backend/tests/test_skill_resolver.py`

- [ ] **Step 1: 写失败测试**

```python
"""Tests for explicit vs automatic skill resolution."""

from app.agent.infrastructure import skill_resolver


INDEX_IDS = ["example_echo", "system_datetime"]


def test_explicit_mode_only_requested() -> None:
    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点",
        requested_skill_ids=["example_echo"],
        index_skill_ids=INDEX_IDS,
    )
    assert out == ["example_echo"]


def test_explicit_ignores_auto_keywords() -> None:
    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点",
        requested_skill_ids=["example_echo"],
        index_skill_ids=INDEX_IDS,
    )
    assert "system_datetime" not in out


def test_auto_matches_system_datetime() -> None:
    out = skill_resolver.resolve_effective_skill_ids(
        user_message="现在几点？",
        requested_skill_ids=[],
        index_skill_ids=INDEX_IDS,
    )
    assert out == ["system_datetime"]


def test_auto_empty_for_unrelated() -> None:
    out = skill_resolver.resolve_effective_skill_ids(
        user_message="你好",
        requested_skill_ids=[],
        index_skill_ids=INDEX_IDS,
    )
    assert out == []
```

- [ ] **Step 2: Run → FAIL**

```bash
cd backend && pytest tests/test_skill_resolver.py -v
```

- [ ] **Step 3: 实现 `skill_resolver.py`**

```python
"""Resolve which skill packs are active for a single agent run."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

SKILL_KEYWORDS: dict[str, list[str]] = {
    "system_datetime": [
        "时间",
        "几点",
        "日期",
        "今天",
        "现在",
        "星期",
        "time",
        "date",
        "datetime",
    ],
}


def match_skills_from_message(user_message: str, index_skill_ids: list[str]) -> list[str]:
    """Heuristic keyword match against registered index ids."""

    msg = user_message or ""
    msg_lower = msg.lower()
    allowed = set(index_skill_ids)
    matched: list[str] = []
    for sid, keywords in SKILL_KEYWORDS.items():
        if sid not in allowed:
            continue
        if any(kw in msg or kw.lower() in msg_lower for kw in keywords):
            matched.append(sid)
    return matched


def resolve_effective_skill_ids(
    *,
    user_message: str,
    requested_skill_ids: list[str],
    index_skill_ids: list[str],
) -> list[str]:
    """Explicit ``requested_skill_ids`` wins; otherwise auto-match from message."""

    allowed = set(index_skill_ids)
    explicit = [s.strip().lower() for s in requested_skill_ids if s and s.strip()]
    if explicit:
        out: list[str] = []
        for sid in explicit:
            if sid not in allowed:
                log.warning("skill id not in index, skipping: %s", sid)
                continue
            out.append(sid)
        return out
    return match_skills_from_message(user_message, index_skill_ids)
```

- [ ] **Step 4: Run → PASS**

```bash
cd backend && pytest tests/test_skill_resolver.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_resolver.py backend/tests/test_skill_resolver.py
git commit -m "feat(agent): add explicit and auto skill resolver"
```

---

### Task 4: `skill_tools` 动态加载

**Files:**
- Create: `backend/app/agent/infrastructure/skill_tools.py`
- Test: `backend/tests/test_skill_tools.py`

- [ ] **Step 1: 写失败测试**

```python
import json

import pytest

from app.agent.infrastructure.skill_tools import load_tools_for_skills
from app.exceptions import AppError


@pytest.mark.asyncio
async def test_load_system_datetime_tool() -> None:
    reg = load_tools_for_skills(["system_datetime"])
    assert reg.has_tool("get_system_datetime")
    raw = await reg.invoke("get_system_datetime", "{}")
    data = json.loads(raw)
    assert "iso" in data
    assert "unix" in data


def test_unknown_skill_skipped() -> None:
    reg = load_tools_for_skills(["not_a_real_skill_xyz"])
    assert reg.get_openai_tools_payload() == []
```

- [ ] **Step 2: Run → FAIL**

```bash
cd backend && pytest tests/test_skill_tools.py -v
```

- [ ] **Step 3: 实现**

```python
"""Load per-skill ``tools.py`` modules and populate a ``ToolRegistry``."""

from __future__ import annotations

import importlib.util
import logging
import re
from pathlib import Path

from app.agent.infrastructure.skill_loader import skills_root
from app.agent.infrastructure.tool_registry import ToolRegistry
from app.exceptions import AppError

log = logging.getLogger(__name__)

_SKILL_ID_RE = re.compile(r"^[a-z0-9_]+$")


def load_tools_for_skills(skill_ids: list[str]) -> ToolRegistry:
    """Import each skill's ``tools.py`` and call ``register(registry)``."""

    registry = ToolRegistry()
    root = skills_root()
    for raw in skill_ids:
        sid = raw.strip().lower()
        if not sid or not _SKILL_ID_RE.fullmatch(sid):
            continue
        tools_path = root / sid / "tools.py"
        if not tools_path.is_file():
            continue
        mod_name = f"agent_skill_{sid}_tools"
        spec = importlib.util.spec_from_file_location(mod_name, tools_path)
        if spec is None or spec.loader is None:
            log.warning("skill tools spec failed skill_id=%s", sid)
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            log.warning("skill tools import failed skill_id=%s err=%s", sid, e)
            continue
        register_fn = getattr(module, "register", None)
        if not callable(register_fn):
            log.warning("skill tools missing register() skill_id=%s", sid)
            continue
        before = set(registry._entries.keys())
        try:
            register_fn(registry)
        except AppError:
            raise
        except Exception as e:
            log.warning("skill tools register failed skill_id=%s err=%s", sid, e)
            continue
        after = set(registry._entries.keys())
        added = after - before
        if len(after) - len(before) != len(added):
            raise AppError(
                "agent.skill.tool_name_conflict",
                f"duplicate tool name while loading skill {sid}",
            )
    return registry
```

**Note:** 若不愿访问 `registry._entries`，可在 `ToolRegistry` 增加 `tool_names() -> list[str]` 并在 register 时检测重复；实现时二选一，保持 `agent.skill.tool_name_conflict`。

- [ ] **Step 4: Run → PASS**

```bash
cd backend && pytest tests/test_skill_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_tools.py backend/tests/test_skill_tools.py
git commit -m "feat(agent): load skill tools.py into ToolRegistry"
```

---

### Task 5: `GET /agent/skills` API

**Files:**
- Modify: `backend/app/agent/api/schemas.py`
- Modify: `backend/app/agent/api/router.py`
- Test: `backend/tests/test_agent_api.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_agent_list_skills_requires_auth() -> None:
    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/workspaces/{ws}/agent/skills")
    assert res.status_code == 401
```

（有 JWT 的集成测可后续补；首期 auth gate 与 sessions 一致。）

- [ ] **Step 2: schemas**

```python
class AgentSkillItemOut(BaseModel):
    """One skill entry from INDEX.md."""

    id: str
    description: str


class AgentSkillListOut(BaseModel):
    """List of skills available in the workspace agent UI."""

    skills: list[AgentSkillItemOut]
```

- [ ] **Step 3: router**

```python
@router.get("/skills", response_model=AgentSkillListOut)
async def list_agent_skills(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> AgentSkillListOut:
    """返回 INDEX 中可加载的技能列表（供前端 ``/`` 菜单）。"""

    rows = skill_loader.list_indexed_skills()
    return AgentSkillListOut(
        skills=[AgentSkillItemOut(id=r["id"], description=r["description"]) for r in rows]
    )
```

在 `router.py` 顶部 `from app.agent.infrastructure import skill_loader`。

- [ ] **Step 4: Run test → PASS**

```bash
cd backend && pytest tests/test_agent_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/api/schemas.py backend/app/agent/api/router.py backend/tests/test_agent_api.py
git commit -m "feat(agent): add GET /agent/skills endpoint"
```

---

### Task 6: `AgentRunService` — resolver + tool 循环

**Files:**
- Modify: `backend/app/agent/service/agent_run_service.py`
- Test: `backend/tests/test_agent_run_tools.py`

- [ ] **Step 1: 写失败测试（mock ChatService）**

```python
"""Agent run tool-loop integration tests with a fake chat stream."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.service.agent_run_service import AgentRunService


def _chunk(*, content: str | None = None, tool_calls: list | None = None, finish: str | None = "stop"):
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class FakeChat:
    def __init__(self, rounds: list[list[dict[str, Any]]]) -> None:
        self._rounds = rounds
        self._i = 0

    async def stream_chunks_messages(self, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        chunks = self._rounds[self._i]
        self._i += 1
        for ch in chunks:
            yield ch


@pytest.mark.asyncio
async def test_tool_loop_invokes_registry_and_second_round(db_session_fixture):
    # Use project DB fixture name from conftest if different
    ...
```

**简化策略：** 若现有 conftest 无 agent DB fixture，可只测 **纯函数级** 抽取：将 `_execute_tool_calls` 留在 service 内，用 mock `registry` + 假 `acc` 测消息持久化逻辑；或 `@pytest.mark.asyncio` + `AsyncMock` 对 `agent_repo` 全部 mock。实现者以「能断言 `stream_chunks_messages` 第二次调用时 `tools` 非 None 且 messages 含 `role=tool`」为目标。

**最小 fake 流：** Round1 单 chunk：

```python
tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "get_system_datetime", "arguments": "{}"}}]
```

Round2：`content="现在是 12:00"`。

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: 修改 `agent_run_service.py`（要点）**

1. 导入 `skill_resolver`, `skill_tools`, `ToolRegistry`, `MinervaToolSnapshot`, `MinervaStreamEventKind`。

2. `idx_text = skill_loader.load_index_text()` 之后：

```python
index_ids = skill_loader.parse_skill_ids_from_index(idx_text)
effective_skill_ids = skill_resolver.resolve_effective_skill_ids(
    user_message=user_message,
    requested_skill_ids=skill_ids,
    index_skill_ids=index_ids,
)
mode = "explicit" if [s for s in skill_ids if s.strip()] else "auto"
# insert skill.auto_resolve node with outputs_json={"mode": mode, "matched_ids": effective_skill_ids}
```

3. 将所有 `for sid in skill_ids:` 改为 `for sid in effective_skill_ids:`。

4. `registry = skill_tools.load_tools_for_skills(effective_skill_ids)`；`tools_arg` / `tool_choice` 如 spec。

5. 抽取 `_stream_one_round(...) -> AsyncIterator[bytes]` 返回 `(acc, emitted)` 或在内层重复代码两次：`round_1` / `round_2`。

6. Round1 结束后 `tool_list = acc.build_tool_calls_list()`：
   - 若空：现有 persist + finish。
   - 若非空且 `registry` 有工具：persist assistant → for tc in tool_list: emit tool.start/result → `append_agent_message(role="tool", ...)` → rebuild `api_messages` from DB → round2。
   - 若 round2 仍有 tool_calls：`agent.tool_loop_exceeded`。

7. **Preview 截断** 辅助函数：

```python
def _preview(s: str, limit: int = 240) -> str:
    return s if len(s) <= limit else s[: limit - 3] + "..."
```

8. 仅当 `tools_arg is None` 且 `tool_list` 非空时走 `agent.unexpected_tool_calls`。

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_agent_run_tools.py tests/test_skill_resolver.py tests/test_skill_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/service/agent_run_service.py backend/tests/test_agent_run_tools.py
git commit -m "feat(agent): effective skill ids and two-round tool loop"
```

---

### Task 7: 前端 API + AgentsPage `/` 菜单

**Files:**
- Modify: `minerva-ui/src/api/agent.ts`
- Modify: `minerva-ui/src/features/workspace/AgentsPage.tsx`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: `agent.ts`**

```typescript
export type AgentSkillListItem = {
  id: string
  description: string
}

/** GET 工作区可用 agent skills（来自服务端 INDEX.md）。 */
export async function listAgentSkills(
  workspaceId: string,
): Promise<{ skills: AgentSkillListItem[] }> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  const res = await fetch(`${origin}/workspaces/${workspaceId}/agent/skills`, { headers })
  // 同 createAgentSession 的 401 / error 处理
  return JSON.parse(text) as { skills: AgentSkillListItem[] }
}
```

- [ ] **Step 2: 辅助函数（AgentsPage 或 `agentSkillUi.ts`）**

```typescript
/** Strip leading `/skill_id` token for API user_message. */
export function stripSkillPrefixFromDraft(draft: string, skillId: string | null): string {
  if (!skillId) return draft.trim()
  const re = new RegExp(`^/?${skillId}\\s*`, 'i')
  return draft.replace(re, '').trim()
}

export function buildDisplayUserMessage(body: string, skillId: string | null): string {
  if (!skillId) return body
  const inner = body.trim()
  return inner ? `/${skillId} ${inner}` : `/${skillId}`
}
```

- [ ] **Step 3: AgentsPage 状态**

```typescript
const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
const skillsQuery = useQuery({
  queryKey: ['agent-skills', workspaceId],
  queryFn: () => listAgentSkills(workspaceId!),
  enabled: Boolean(workspaceId),
})
```

- `draft.startsWith('/')` 时显示 `Dropdown`/`Popover` 列表：`skillsQuery.data?.skills`，过滤 `draft.slice(1).toLowerCase()` 匹配 id/description。

- 点击项：`setSelectedSkillId(item.id)`；`setDraft(\`/${item.id} \`)`。

- `onSend`：
  - `const apiBody = stripSkillPrefixFromDraft(draft, selectedSkillId)`
  - `const displayContent = buildDisplayUserMessage(apiBody, selectedSkillId)`
  - user bubble `content: displayContent`
  - `streamAgentRun(..., { user_message: apiBody || displayContent, skill_ids: selectedSkillId ? [selectedSkillId] : [] })`
  - 发送后 `setSelectedSkillId(null)`

- [ ] **Step 4: i18n**

`zh-CN.json` / `en.json` 增加：

- `agents.skillPickerTitle`
- `agents.skillPickerEmpty`
- `agents.skillLoading`

- [ ] **Step 5: 手动验证**

1. 打开 Agents 页，输入 `/`，应看到 `system_datetime` 等（来自 API）。
2. 选择后发送「现在几点」→ Network 中 `skill_ids: ["system_datetime"]`，`user_message` 无重复前缀。
3. 不选 skill，直接发「现在几点」→ `skill_ids: []`，后端自动匹配仍应触发 tool。

- [ ] **Step 6: Commit**

```bash
git add minerva-ui/src/api/agent.ts minerva-ui/src/features/workspace/AgentsPage.tsx minerva-ui/src/i18n
git commit -m "feat(ui): dynamic agent skill picker and skill_ids on run"
```

---

### Task 8: 全量回归

- [ ] **Step 1: Backend**

```bash
cd backend && pytest tests/test_skill_loader.py tests/test_skill_resolver.py tests/test_skill_tools.py tests/test_agent_api.py tests/test_agent_run_tools.py tests/test_agent_stream_accumulator.py -v
```

- [ ] **Step 2: 更新 spec 状态（可选）**

将 `docs/superpowers/specs/2026-05-16-agent-system-datetime-skill-design.md` 顶部 **状态** 改为「已实现」。

- [ ] **Step 3: Commit（若有 spec 状态变更）**

```bash
git add docs/superpowers/specs/2026-05-16-agent-system-datetime-skill-design.md
git commit -m "docs(agent): mark system_datetime skill spec as implemented"
```

---

## Self-review（plan vs spec）

| Spec 要求 | Task |
|-----------|------|
| `system_datetime` SKILL + tools | Task 1 |
| 显式仅请求 skill / 自动关键词 | Task 3, 6 |
| `skill_tools` importlib 加载 | Task 4 |
| 2-round tool loop + SSE tool.start/result | Task 6 |
| `GET /agent/skills` 动态列表 | Task 2, 5 |
| 前端 `/` 单选、气泡带前缀、API 剥离 | Task 7 |
| 错误码 tool_loop_exceeded / tool_name_conflict | Task 4, 6 |
| 注释规范 | 各 Task 注明 |

**Placeholder scan:** 无 TBD。Task 6 DB fixture 名由实现者对照 `backend/tests/conftest.py` 确定，属环境绑定而非占位。

---

## 执行交接

**Plan 已保存至** `docs/superpowers/plans/2026-05-16-agent-system-datetime-skill.md`。

**两种执行方式（二选一）：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间复核；使用 `superpowers:subagent-driven-development`。
2. **Inline Execution** — 本会话按 Task 顺序实现；使用 `superpowers:executing-plans` 做批次检查点。

你想用哪种？若直接开始，回复 **「在本会话按 Task 1 开始实现」** 即可。
