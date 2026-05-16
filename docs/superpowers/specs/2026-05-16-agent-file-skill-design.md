# Agent `file` 技能：工作区本地沙箱文件 CRUD 设计说明

**日期**：2026-05-16  
**状态**：待实现  
**范围**：新增 `file` 技能包（细粒度多工具）；实现 `AgentFileSandbox` 与 `SkillToolContext`；扩展 `load_tools_for_skills` / `AgentRunService` 注入 `workspace_id`；注册 `INDEX.md` 与 `skill_resolver` 关键词。

**关系**：本设计为 `docs/superpowers/specs/2026-05-16-agent-system-datetime-skill-design.md` 的 **增量**，复用既有技能加载、工具循环、skills HTTP API 与前端 `/` 菜单机制。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `backend/app/agent/skills/file/` 实现工作区隔离的**服务端本地沙箱**文件与目录操作，技能 id 为 **`file`**，并注册到 `skills/INDEX.md`。
- 采用 **沙箱服务 + 薄 tools**（`AgentFileSandbox` + `file/tools.py` 注册 6 个 OpenAI function tools）。
- 路径模型：**仅沙箱内相对路径**（`path` / `src`+`dest`），禁止 `..`、绝对路径、`~` 等；沙箱根为 `{agent_files_root}/workspaces/{workspace_id}/`。
- 通过 **`SkillToolContext(workspace_id)`** 在 `load_tools_for_skills` 时注入 run 上下文；`system_datetime` 等现有技能保持 `register(registry)` 单参数签名，**向后兼容**。
- 模型根据用户意图自动选择工具：`list_dir`、`read_file`、`write_file`、`delete_path`、`mkdir`、`move_path`（`tool_choice: auto`）。

### 1.2 成功标准

- 用户 `/file` 或自动匹配（如「读取 notes/readme.md」）后，模型可调用沙箱工具，SSE 出现 `tool.start` / `tool.result`，助手回复与磁盘内容一致。
- `write_file` 后 `read_file` 可读到相同 UTF-8 内容；`list_dir` 能列出新建目录。
- 工作区 A 的 Agent **无法**通过 `../` 或其它方式访问工作区 B 的沙箱文件。
- `GET /workspaces/{workspace_id}/agent/skills` 动态返回含 `file` 的列表（来自 `INDEX.md`，前端不硬编码 id）。

### 1.3 非目标

- 工作区 **S3** / `S3FileService` 集成。
- 独立 REST「工作区沙箱文件」管理 API（仅 Agent 工具访问）。
- 二进制 / Base64 读写；全文搜索；文件 watch；细粒度 ACL。
- 将 `agent_max_tool_rounds` 从固定 2 轮改为可配置循环（若联调不足，另开任务；本技能单轮可并行多个 `tool_calls`）。

---

## 2. 架构

### 2.1 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| 运行上下文 | `backend/app/agent/infrastructure/skill_tool_context.py` | `SkillToolContext(workspace_id: UUID)` |
| 沙箱服务 | `backend/app/agent/infrastructure/agent_file_sandbox.py` | 路径解析、防穿越、6 类 FS 操作 |
| 技能工具 | `backend/app/agent/skills/file/tools.py` | `register(registry, ctx)`，绑定 6 个 handler |
| 技能说明 | `backend/app/agent/skills/file/SKILL.md` | 何时调用、路径规则、工具一览 |
| 加载器 | `skill_tools.py` | `load_tools_for_skills(skill_ids, *, ctx=...)`，按签名调用 `register` |
| 解析器 | `skill_resolver.py` | `SKILL_KEYWORDS["file"]` |
| 配置 | `app/config.py` | `agent_files_root`、`agent_file_max_bytes` |
| Run 服务 | `agent_run_service.py` | 构造 `SkillToolContext` 并传入 loader |

### 2.2 数据流

```text
POST run (workspace_id, user_message, skill_ids?)
  → resolve_effective_skill_ids（显式或关键词命中 file）
  → load_tools_for_skills(ids, ctx=SkillToolContext(workspace_id))
  → file/tools.register → 6 tools on ToolRegistry
  → LLM round_1（tools=auto）→ tool_calls
  → registry.invoke → AgentFileSandbox(workspace_id).*
  → JSON tool result → round_2 assistant
```

### 2.3 沙箱目录布局

```text
{agent_files_root}/                    # 默认 backend/data/agent-files
  workspaces/
    {workspace_id}/                    # 该工作区沙箱根（模型 path="" 或 ".")
      notes/readme.md
      ...
```

- `agent_files_root` 可通过环境变量 `AGENT_FILES_ROOT` 配置。
- 首次需要时创建 `workspaces/{workspace_id}/`（`mkdir(parents=True, exist_ok=True)`）。

---

## 3. 路径安全（`AgentFileSandbox.resolve`）

1. `strip()`；`""` 与 `"."` 表示工作区沙箱根。
2. 统一 `/` 分隔；去掉首尾 `/`（根目录除外）。
3. **拒绝**：含 `..`、反斜杠 `\`、以 `/` 开头、盘符形式（如 `C:`）、`~`、空段、NUL。
4. 拼接 `workspace_root = agent_files_root / "workspaces" / str(workspace_id)` 与相对段。
5. `resolved = (...).resolve()`，必须 `resolved.is_relative_to(workspace_root.resolve())`，否则 `path_outside_sandbox`。
6. 单段名长度 ≤ 255，全路径字符长度 ≤ 4096，否则 `path_invalid`。

所有工具的路径参数均经同一 `resolve` 逻辑。

---

## 4. 工具契约

统一返回 **JSON 字符串**。成功含 `"ok": true`；失败含 `"ok": false`, `"error"`, `"code"`（不依赖未捕获异常进入 tool 循环）。

Handler 为 `async def`；内部同步 FS 使用 `asyncio.to_thread` 执行，避免阻塞事件循环。

### 4.1 `list_dir`

| 字段 | 说明 |
|------|------|
| 参数 | `path: string`（默认 `""`） |
| 行为 | 仅列**直接子项**（不递归） |
| 成功 | `{ "ok": true, "path": "<relative>", "entries": [ { "name", "type": "file"\|"dir", "size": <int>? } ] }` |
| 错误码 | `not_found`, `not_a_directory` |

### 4.2 `read_file`

| 字段 | 说明 |
|------|------|
| 参数 | `path: string` |
| 行为 | 读取 UTF-8 文本；超过 `agent_file_max_bytes` 拒绝 |
| 成功 | `{ "ok": true, "path", "content", "size" }` |
| 错误码 | `not_found`, `is_directory`, `too_large`, `not_utf8` |

### 4.3 `write_file`

| 字段 | 说明 |
|------|------|
| 参数 | `path`, `content`；`create_parents: boolean`（默认 `true`） |
| 行为 | 创建或**覆盖**；`content` 按 UTF-8 写入，编码后字节 ≤ `agent_file_max_bytes` |
| 成功 | `{ "ok": true, "path", "size", "created": <bool> }`（`created` 表示此前不存在） |
| 错误码 | `is_directory`, `too_large` |

### 4.4 `delete_path`

| 字段 | 说明 |
|------|------|
| 参数 | `path`；`recursive: boolean`（默认 `false`） |
| 行为 | 删文件；删目录时空目录直接删，非空目录需 `recursive=true` |
| 成功 | `{ "ok": true, "path", "deleted": true }` |
| 错误码 | `not_found`, `directory_not_empty` |

### 4.5 `mkdir`

| 字段 | 说明 |
|------|------|
| 参数 | `path`；`parents: boolean`（默认 `true`） |
| 行为 | 创建目录；已存在且为目录时 `ok: true`（幂等） |
| 成功 | `{ "ok": true, "path", "created": <bool> }` |
| 错误码 | `already_exists`（路径已存在且为文件） |

### 4.6 `move_path`

| 字段 | 说明 |
|------|------|
| 参数 | `src`, `dest`（均为相对路径） |
| 行为 | `Path.rename`；`dest` 父目录不存在时失败（不自动建父目录，避免误移） |
| 成功 | `{ "ok": true, "src", "dest" }` |
| 错误码 | `not_found`, `dest_exists`, `path_outside_sandbox` |

---

## 5. 配置

| 设置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| `agent_files_root` | `AGENT_FILES_ROOT` | `{backend}/data/agent-files` | 沙箱顶层目录 |
| `agent_file_max_bytes` | `AGENT_FILE_MAX_BYTES` | `524288` (512 KiB) | 单文件读/写上限 |

---

## 6. `file` 技能包

### 6.1 目录

```text
backend/app/agent/skills/
  INDEX.md
  file/
    SKILL.md
    tools.py
```

### 6.2 `INDEX.md` 条目

```markdown
- `file`：工作区沙箱内文件与目录的读写与管理（相对路径）。
```

### 6.3 `SKILL.md` 要点

- 用户要求读/写/列目录/删除/建目录/移动或重命名**工作区本地文件**时，**必须**调用对应工具，**不得**臆造文件内容或目录结构。
- 路径一律为沙箱内相对路径；不确定路径时先 `list_dir`。
- 说明 UTF-8 文本与大小限制；非文本或超大文件应告知用户无法通过本技能处理。

### 6.4 `tools.py`

```python
def register(registry: ToolRegistry, ctx: SkillToolContext | None = None) -> None:
    ...
```

- `ctx` 为 `None` 时：handler 返回 `{"ok": false, "code": "no_workspace_context", ...}`（便于单测 import，不在生产 run 中出现）。
- 使用 `AgentFileSandbox(ctx.workspace_id)` 执行操作。

---

## 7. 加载与集成

### 7.1 `skill_tools.load_tools_for_skills`

```python
def load_tools_for_skills(
    skill_ids: list[str],
    *,
    ctx: SkillToolContext | None = None,
) -> ToolRegistry:
```

对每个 `tools.py` 的 `register`：

- 若 `inspect.signature(register).parameters` 包含 `ctx`（或第二位置参数），调用 `register(registry, ctx)`。
- 否则 `register(registry)`。

### 7.2 `AgentRunService`

在现有 `load_tools_for_skills(effective_skill_ids)` 处改为：

```python
registry = skill_tools.load_tools_for_skills(
    effective_skill_ids,
    ctx=SkillToolContext(workspace_id=workspace_id),
)
```

### 7.3 `skill_resolver.SKILL_KEYWORDS`

`file` 关键词（中英文，可扩展）：

`文件`, `目录`, `文件夹`, `读取`, `写入`, `保存`, `删除`, `创建`, `重命名`, `移动`, `列出`, `list`, `read`, `write`, `mkdir`, `delete`, `move`, `file`, `folder`, `directory`

---

## 8. 测试

| 文件 | 覆盖点 |
|------|--------|
| `test_agent_file_sandbox.py` | `resolve` 拒绝 `../`；两 `workspace_id` 互不可见；六类操作 happy path；`too_large`；非 UTF-8 |
| `test_skill_tools.py` | `load_tools_for_skills(["file"], ctx=...)` 注册 6 工具名 |
| `test_skill_resolver.py` | 空 `skill_ids` +「读取文件」→ `file` |
| `test_skill_loader.py` | INDEX 含 `file` |
| `test_agent_api.py` | `GET .../agent/skills` 含 `file` |

测试使用 `tmp_path` 或 `monkeypatch` 覆盖 `settings.agent_files_root`，不写入仓库 `data/` 目录。

---

## 9. 错误码汇总（工具 JSON `code`）

| code | 含义 |
|------|------|
| `path_invalid` | 非法路径字符或超长 |
| `path_outside_sandbox` | 解析后逃出工作区根 |
| `not_found` | 路径不存在 |
| `not_a_directory` | 期望目录实为文件 |
| `is_directory` | 期望文件实为目录 |
| `directory_not_empty` | 非空目录且 `recursive=false` |
| `dest_exists` | `move_path` 目标已存在 |
| `already_exists` | `mkdir` 路径为已存在文件 |
| `too_large` | 超过 `agent_file_max_bytes` |
| `not_utf8` | 非 UTF-8 文本 |
| `no_workspace_context` | 无 `ctx`（仅测试/误用） |

---

## 10. 实现顺序建议

1. `Settings` 增加 `agent_files_root`、`agent_file_max_bytes`
2. `skill_tool_context.py` + `agent_file_sandbox.py` + `test_agent_file_sandbox.py`
3. `skill_tools.py` 扩展 `ctx` + `test_skill_tools.py` 更新
4. `file/SKILL.md`、`file/tools.py`、`INDEX.md`
5. `skill_resolver` 关键词 + 单测
6. `AgentRunService` 传入 `SkillToolContext`
7. `test_skill_loader` / `test_agent_api` 更新
8. 手动：前端 `/file` → 写入并读取文件 → 检查 SSE tool 事件

---

## 11. 与既有 spec 的关系

- 不修改 `GET .../agent/skills` 契约与前端 `/` 交互。
- 不引入新 SSE 事件类型。
- 工具循环轮次与 `system_datetime` 设计一致（当前实现为 2 轮 LLM）；多步文件任务依赖单轮多 `tool_calls` 或第二轮汇总。
