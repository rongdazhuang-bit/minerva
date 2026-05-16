# Agent `file` 技能（工作区本地沙箱 CRUD）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 `file` 技能包、按 `workspace_id` 隔离的服务端沙箱文件 CRUD（6 个细粒度工具），并通过 `SkillToolContext` 注入 run 上下文，使 Agent 在显式 `/file` 或自动匹配时可安全读写工作区相对路径。

**Architecture:** `AgentFileSandbox` 集中路径解析与 FS；`file/tools.py` 仅注册 OpenAI function tools；`load_tools_for_skills(..., ctx=SkillToolContext(workspace_id))` 向后兼容 `system_datetime` 单参数 `register`；`skill_resolver` 增加 `file` 关键词；配置项 `agent_files_root` / `agent_file_max_bytes` 控制根目录与大小上限。

**Tech Stack:** Python 3.12 / FastAPI / pathlib / asyncio.to_thread / pytest

**Spec:** `docs/superpowers/specs/2026-05-16-agent-file-skill-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/config.py` | `agent_files_root`, `agent_file_max_bytes` |
| `backend/app/agent/infrastructure/skill_tool_context.py` | `SkillToolContext` dataclass |
| `backend/app/agent/infrastructure/agent_file_sandbox.py` | 沙箱路径解析 + 6 类 FS |
| `backend/app/agent/infrastructure/skill_tools.py` | 可选 `ctx` 传入 `register` |
| `backend/app/agent/skills/file/SKILL.md` | 技能说明 |
| `backend/app/agent/skills/file/tools.py` | 6 tools + `register(registry, ctx)` |
| `backend/app/agent/skills/INDEX.md` | 注册 `file` |
| `backend/app/agent/infrastructure/skill_resolver.py` | `SKILL_KEYWORDS["file"]` |
| `backend/app/agent/service/agent_run_service.py` | 构造 `SkillToolContext` |
| `backend/tests/test_agent_file_sandbox.py` | 沙箱单测 |
| `backend/tests/test_skill_tools.py` | 加载 `file` + ctx |
| `backend/tests/test_skill_resolver.py` | 自动匹配 `file` |
| `backend/tests/test_skill_loader.py` | INDEX / SKILL.md |
| `backend/tests/test_agent_api.py` | （可选）skills 列表含 `file` 的集成测 |

**Note:** `skills/file/` 无 `__init__.py`；`skill_tools` 继续用 `importlib.util.spec_from_file_location` 加载 `tools.py`。

---

### Task 1: 配置项

**Files:**
- Modify: `backend/app/config.py`（在 `agent_tool_timeout_seconds` 附近追加字段）

- [ ] **Step 1: 在 `Settings` 增加字段**

在 `backend/app/config.py` 的 `Settings` 类中、`agent_tool_timeout_seconds` 之后添加：

```python
    agent_files_root: str = Field(
        default="",
        description="Agent 工作区文件沙箱根目录；空则使用 backend/data/agent-files。",
        validation_alias=AliasChoices("AGENT_FILES_ROOT", "agent_files_root"),
    )
    agent_file_max_bytes: int = Field(
        default=524288,
        ge=1024,
        description="Agent file 技能单文件读/写最大字节数。",
        validation_alias=AliasChoices("AGENT_FILE_MAX_BYTES", "agent_file_max_bytes"),
    )
```

- [ ] **Step 2: 添加解析函数（模块级，紧挨 `settings = Settings()` 之前）**

```python
def resolve_agent_files_root() -> Path:
    """Return configured agent files root, defaulting to ``backend/data/agent-files``."""

    raw = (settings.agent_files_root or "").strip()
    if raw:
        return Path(raw).resolve()
    return (_BACKEND_DIR / "data" / "agent-files").resolve()
```

将 `from pathlib import Path` 确保已在文件顶部（已有 `_BACKEND_DIR` 时通常已有 `Path`）。

- [ ] **Step 3: 验证 import**

Run: `cd backend && python -c "from app.config import settings, resolve_agent_files_root; print(resolve_agent_files_root())"`

Expected: 打印绝对路径，以 `agent-files` 结尾。

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(agent): add agent file sandbox settings"
```

---

### Task 2: `SkillToolContext` + `AgentFileSandbox`（TDD）

**Files:**
- Create: `backend/app/agent/infrastructure/skill_tool_context.py`
- Create: `backend/app/agent/infrastructure/agent_file_sandbox.py`
- Create: `backend/tests/test_agent_file_sandbox.py`

- [ ] **Step 1: 编写 `skill_tool_context.py`**

```python
"""Run-scoped context passed into skill tool registration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillToolContext:
    """Immutable context for one agent run's tool handlers."""

    workspace_id: uuid.UUID
```

- [ ] **Step 2: 编写失败测试 `test_agent_file_sandbox.py`（节选核心用例）**

```python
"""Tests for workspace-scoped agent file sandbox."""

from __future__ import annotations

import uuid

import pytest

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.config import settings


@pytest.fixture
def sandbox_root(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> object:
    """Point agent files root at a temp directory."""

    root = tmp_path / "agent-files"
    monkeypatch.setattr(settings, "agent_files_root", str(root))
    return root


def test_resolve_rejects_parent_traversal(sandbox_root: object) -> None:
    """Paths with ``..`` are rejected."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box.resolve("../etc/passwd")
    assert exc.value.code == "path_invalid"


def test_workspace_isolation(sandbox_root: object) -> None:
    """Two workspaces cannot read each other's files."""

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    box_a = AgentFileSandbox(workspace_id=ws_a)
    box_b = AgentFileSandbox(workspace_id=ws_b)
    box_a.write_file("secret.txt", "alpha")
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box_b.read_file("secret.txt")
    assert exc.value.code == "not_found"


@pytest.mark.asyncio
async def test_write_read_roundtrip(sandbox_root: object) -> None:
    """write_file then read_file returns same UTF-8 text."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    w = await box.write_file_async("notes/a.txt", "hello 文件")
    assert w["ok"] is True
    r = await box.read_file_async("notes/a.txt")
    assert r["ok"] is True
    assert r["content"] == "hello 文件"
```

在文件顶部为 `AgentFileSandbox` 预留 `Error` 异常类（实现 Task 2 Step 4 时添加）。

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && pytest tests/test_agent_file_sandbox.py -v`

Expected: FAIL（`ModuleNotFoundError` 或 `AgentFileSandbox` 未定义）

- [ ] **Step 4: 实现 `agent_file_sandbox.py`**

实现要点（完整代码由执行者写入单文件，须包含）：

1. **异常** `class Error(Exception)`，属性 `code: str`, `message: str`；`to_dict() -> dict` 返回 `{"ok": False, "error": message, "code": code}`。

2. **`AgentFileSandbox.__init__(self, *, workspace_id: uuid.UUID)`**  
   - `self._workspace_id = workspace_id`  
   - `self._root = resolve_agent_files_root() / "workspaces" / str(workspace_id)`

3. **`workspace_root(self) -> Path`**：确保目录存在并返回 `self._root`。

4. **`resolve(self, path: str) -> Path`**：按 spec §3 规范化；失败抛 `Error`（`path_invalid` / `path_outside_sandbox`）。

5. **同步方法**（返回 `dict`，成功含 `"ok": True`）：  
   `list_dir`, `read_file`, `write_file`, `delete_path`, `mkdir`, `move_path`  
   参数与 spec §4 一致；`write_file` 的 `create_parents: bool = True`；`delete_path` 的 `recursive: bool = False`；`mkdir` 的 `parents: bool = True`。

6. **异步包装**（供 tools 调用）：

```python
async def read_file_async(self, path: str) -> dict:
    """Run ``read_file`` in a worker thread."""

    import asyncio
    return await asyncio.to_thread(self.read_file, path)
```

对其余 5 个操作同样提供 `*_async`（或统一 `_run(name, **kwargs)`）。

7. **`read_file`**：仅 UTF-8；`UnicodeDecodeError` → `not_utf8`；大小用 `agent_file_max_bytes`。

8. **`move_path`**：`dest` 父目录必须已存在，否则 `not_found`（父目录缺失）。

路径规范化辅助函数示例：

```python
def _normalize_relative_path(path: str) -> str:
    """Normalize user path to a safe relative form (may be empty for root)."""

    raw = (path or "").strip().replace("\\", "/")
    if raw in ("", "."):
        return ""
    while raw.startswith("/"):
        raw = raw[1:]
    if ".." in raw.split("/"):
        raise AgentFileSandbox.Error("path_invalid", "path must not contain '..'")
    return raw
```

`resolve` 末尾：

```python
resolved = (workspace_root / Path(*parts)).resolve()
if not resolved.is_relative_to(workspace_root.resolve()):
    raise AgentFileSandbox.Error("path_outside_sandbox", "path outside workspace sandbox")
return resolved
```

（`parts` 来自 `normalized.split("/")` 过滤空串。）

- [ ] **Step 5: 补全测试并运行**

在 `test_agent_file_sandbox.py` 增加：`list_dir` 列项、`delete_path` 非空目录需 `recursive`、`too_large`（`monkeypatch` `settings.agent_file_max_bytes = 4`）。

Run: `cd backend && pytest tests/test_agent_file_sandbox.py -v`

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/infrastructure/skill_tool_context.py \
  backend/app/agent/infrastructure/agent_file_sandbox.py \
  backend/tests/test_agent_file_sandbox.py \
  backend/app/config.py
git commit -m "feat(agent): add workspace file sandbox service"
```

---

### Task 3: 扩展 `skill_tools` 注入 `ctx`

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_tools.py`
- Modify: `backend/tests/test_skill_tools.py`

- [ ] **Step 1: 修改 `load_tools_for_skills` 签名与调用**

```python
import inspect
from app.agent.infrastructure.skill_tool_context import SkillToolContext

def load_tools_for_skills(
    skill_ids: list[str],
    *,
    ctx: SkillToolContext | None = None,
) -> ToolRegistry:
```

在 `register_fn(registry)` 处改为：

```python
        params = inspect.signature(register_fn).parameters
        if len(params) >= 2:
            register_fn(registry, ctx)
        else:
            register_fn(registry)
```

- [ ] **Step 2: 增加测试**

在 `backend/tests/test_skill_tools.py` 追加：

```python
import uuid
from app.agent.infrastructure.skill_tool_context import SkillToolContext

@pytest.mark.asyncio
async def test_load_file_tools_with_context(tmp_path, monkeypatch) -> None:
    """file skill registers six tools when ctx is provided."""

    from app.config import settings

    monkeypatch.setattr(settings, "agent_files_root", str(tmp_path / "af"))
    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    reg = load_tools_for_skills(["file"], ctx=ctx)
    for name in (
        "list_dir",
        "read_file",
        "write_file",
        "delete_path",
        "mkdir",
        "move_path",
    ):
        assert reg.has_tool(name), name
    raw = await reg.invoke(
        "write_file",
        '{"path": "t.txt", "content": "x"}',
    )
    data = json.loads(raw)
    assert data.get("ok") is True
```

（实现 `file/tools.py` 前本测试会 FAIL — 可先完成 Task 4 再跑，或 Task 3+4 同一 PR。）

- [ ] **Step 3: 确认 `system_datetime` 仍通过**

Run: `cd backend && pytest tests/test_skill_tools.py -v`

Expected: PASS（含原 `test_load_system_datetime_tool`）

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/skill_tools.py backend/tests/test_skill_tools.py
git commit -m "feat(agent): pass SkillToolContext into skill tool registration"
```

---

### Task 4: `file` 技能包 + INDEX

**Files:**
- Create: `backend/app/agent/skills/file/SKILL.md`
- Create: `backend/app/agent/skills/file/tools.py`
- Modify: `backend/app/agent/skills/INDEX.md`
- Modify: `backend/tests/test_skill_loader.py`

- [ ] **Step 1: 更新 INDEX**

在 `backend/app/agent/skills/INDEX.md` 增加：

```markdown
- `file`：工作区沙箱内文件与目录的读写与管理（相对路径）。
```

- [ ] **Step 2: 编写 `SKILL.md`**

说明：读写删建目录/移动时必须调用工具；仅相对路径；先 `list_dir` 再操作不确定路径；UTF-8 与大小限制。

- [ ] **Step 3: 编写 `tools.py`**

结构：

```python
"""Executable tools for the ``file`` agent skill."""

from __future__ import annotations

import json
import uuid

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.infrastructure.tool_registry import ToolRegistry


def _box(ctx: SkillToolContext | None) -> AgentFileSandbox:
    """Build sandbox or raise via JSON error when context is missing."""

    if ctx is None:
        raise RuntimeError("no_workspace_context")
    return AgentFileSandbox(workspace_id=ctx.workspace_id)


async def _json_call(ctx: SkillToolContext | None, fn, **kwargs: object) -> str:
    """Invoke sandbox async helper and return JSON string."""

    if ctx is None:
        return json.dumps(
            {
                "ok": False,
                "code": "no_workspace_context",
                "error": "workspace context is required",
            },
            ensure_ascii=False,
        )
    try:
        box = AgentFileSandbox(workspace_id=ctx.workspace_id)
        result = await fn(box, **kwargs)
        return json.dumps(result, ensure_ascii=False)
    except AgentFileSandbox.Error as e:
        return json.dumps(e.to_dict(), ensure_ascii=False)


def register(registry: ToolRegistry, ctx: SkillToolContext | None = None) -> None:
    """Register file sandbox tools on ``registry``."""

    async def list_dir(path: str = "") -> str:
        return await _json_call(ctx, lambda b, **kw: b.list_dir_async(**kw), path=path)

    # ... 同理 read_file(path), write_file(path, content, create_parents=True), etc.

    registry.register("list_dir", list_dir, description="列出沙箱目录下的直接子项。", parameters={...})
    # ... 共 6 个 register，parameters 与 spec §4 一致
```

每个 handler 调用对应 `box.*_async`；`parameters` 使用 JSON Schema `type`/`properties`/`required`。

- [ ] **Step 4: 扩展 `test_skill_loader.py`**

```python
def test_parse_skill_ids_finds_file() -> None:
    text = skill_loader.load_index_text()
    ids = skill_loader.parse_skill_ids_from_index(text)
    assert "file" in ids


def test_load_skill_markdown_file() -> None:
    body = skill_loader.load_skill_markdown("file")
    assert len(body.strip()) > 0
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest tests/test_skill_loader.py tests/test_skill_tools.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/skills/file backend/app/agent/skills/INDEX.md backend/tests/test_skill_loader.py
git commit -m "feat(agent): add file skill pack with sandbox tools"
```

---

### Task 5: `skill_resolver` 关键词

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_resolver.py`
- Modify: `backend/tests/test_skill_resolver.py`

- [ ] **Step 1: 在 `SKILL_KEYWORDS` 增加 `file`**

```python
    "file": [
        "文件",
        "目录",
        "文件夹",
        "读取",
        "写入",
        "保存",
        "删除",
        "创建",
        "重命名",
        "移动",
        "列出",
        "list",
        "read",
        "write",
        "mkdir",
        "delete",
        "move",
        "file",
        "folder",
        "directory",
    ],
```

- [ ] **Step 2: 更新测试 INDEX_IDS**

```python
INDEX_IDS = ["example_echo", "system_datetime", "file"]
```

新增：

```python
def test_auto_matches_file() -> None:
    out = skill_resolver.resolve_effective_skill_ids(
        user_message="请读取 notes/readme.md",
        requested_skill_ids=[],
        index_skill_ids=INDEX_IDS,
    )
    assert out == ["file"]
```

- [ ] **Step 3: 运行**

Run: `cd backend && pytest tests/test_skill_resolver.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/skill_resolver.py backend/tests/test_skill_resolver.py
git commit -m "feat(agent): auto-resolve file skill from message keywords"
```

---

### Task 6: `AgentRunService` 传入上下文

**Files:**
- Modify: `backend/app/agent/service/agent_run_service.py`

- [ ] **Step 1: 增加 import**

```python
from app.agent.infrastructure.skill_tool_context import SkillToolContext
```

- [ ] **Step 2: 替换 `load_tools_for_skills` 调用**

将：

```python
registry = skill_tools.load_tools_for_skills(effective_skill_ids)
```

改为：

```python
registry = skill_tools.load_tools_for_skills(
    effective_skill_ids,
    ctx=SkillToolContext(workspace_id=workspace_id),
)
```

- [ ] **Step 3: 运行相关测试**

Run: `cd backend && pytest tests/test_skill_tools.py tests/test_skill_resolver.py tests/test_agent_file_sandbox.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/service/agent_run_service.py
git commit -m "feat(agent): inject workspace id into skill tool handlers"
```

---

### Task 7: 回归与手动验证

- [ ] **Step 1: 全量 agent 相关测试**

Run: `cd backend && pytest tests/test_skill_loader.py tests/test_skill_tools.py tests/test_skill_resolver.py tests/test_agent_file_sandbox.py tests/test_agent_api.py -v`

Expected: PASS

- [ ] **Step 2: 手动验证（本地 dev）**

1. 启动 API；打开 Agents 页，`/` 选择 `file`（描述来自 API）。
2. 发送：`/file 在 notes 下创建 hello.txt，内容为 hello`。
3. 确认 SSE 含 `tool.start` / `tool.result`（`write_file` 或 `mkdir` + `write_file`）。
4. 再发：`/file 读取 notes/hello.txt` → 助手引用 `read_file` 结果。
5. 检查磁盘：`backend/data/agent-files/workspaces/<workspace_id>/notes/hello.txt` 存在。

- [ ] **Step 3: 最终 commit（若 Step 1–6 已分批提交可跳过）**

---

## Plan self-review（对照 spec）

| Spec 章节 | 任务 |
|-----------|------|
| §1 目标 / 成功标准 | Task 4–7 |
| §2 架构 / 数据流 | Task 2, 3, 6 |
| §3 路径安全 | Task 2 `resolve` + tests |
| §4 六工具契约 | Task 2, 4 |
| §5 配置 | Task 1 |
| §6 技能包 | Task 4 |
| §7 加载与集成 | Task 3, 5, 6 |
| §8 测试 | Task 2, 3, 4, 5, 7 |
| §9 错误码 | Task 2 `Error.code` |
| §10 实现顺序 | Task 1→7 |

无 TBD；`move_path` 不自动建父目录已在 Task 2 说明。

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-agent-file-skill.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立子代理，任务间你做 review，迭代快。  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，批次间设检查点。

你想用哪种方式？若直接开始实现，回复 **「inline」** 或 **「subagent」** 即可。
