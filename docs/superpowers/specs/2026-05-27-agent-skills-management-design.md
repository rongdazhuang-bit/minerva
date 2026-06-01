# Agent 技能管理（全局 skills 目录 CRUD UI）设计说明

**日期**：2026-05-27  
**状态**：已批准，待实现  
**范围**：租户 owner/admin 通过 frontend「智能体 > 技能」管理服务端全局内置目录 `backend/app/agent/skills/`；含 zip 上传技能包、文件树浏览、`.md`/`.py`/`.json` 在线编辑、二进制文件上传/下载/删除；保存后立即刷新 `skill_loader` 缓存。

**关系**：扩展 `docs/agent-module-design.md` §1.4 原「非目标：用户上传自定义 Skill 包」；与现有只读 `GET /agent/v2/skills` 及 `skill_loader.py` 协同。

---

## 1. 目标与成功标准

### 1.1 目标

- 替换占位页 `AgentSkillsPage.tsx`，提供两级导航：**技能列表** → **技能详情（文件树 + 编辑器）**。
- 后端新增 `skills-mgmt` API，直接读写 `skills_root()`（`backend/app/agent/skills/`），变更对所有工作区生效。
- 权限：**租户 owner 或 admin**（通过当前 `workspace_id` 解析 `tenant_id`，查 `TenantMembership.role`）。
- 上传 zip 技能包：根目录须为**单个文件夹**；校验 `skill_id` 不重名；必须含 `SKILL.md`。
- 文本编辑：`.md`、`.py`、`.json` 使用 Monaco 不同 language 模式；其余文件仅上传/下载/删除。
- 写操作后立即调用 `invalidate_skill_cache()`，无需重启服务。

### 1.2 成功标准

- 租户 admin 可上传新技能 zip，列表出现新 skill，Agent Run 可路由到新 skill。
- 编辑 `INDEX.md` 或 `SKILL.md` 保存后，`GET /agent/v2/skills` 返回更新后的描述/顺序。
- 编辑 `tools.py` 保存后，下一次 Run 加载新工具（`importlib` 缓存已失效）。
- 租户 member 访问写接口返回 403；路径穿越请求返回 400。
- 删除内置 skill（如 `general`）允许执行；`skill_loader` fallback 仍可发现含 `SKILL.md` 的目录。

### 1.3 非目标（本期）

- Git 版本历史 / diff
- 技能在线调试 / 试运行
- 工作区级自定义 skill 目录
- Python 语法静态检查
- 文件编辑乐观锁 / 协同编辑
- 向量检索或 DB 镜像技能元数据

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. Filesystem API + 两级 UI** | `SkillFilesService` 封装 FS 操作 + 前端两级导航 | **采用** |
| B. Git 版本管理 | UI 只做 git commit/rollback | 部署复杂，不符需求 |
| C. DB 镜像 + 同步 | 元数据存 DB 再同步 FS | 过度设计 |

---

## 3. 后端设计

### 3.1 模块

```
backend/app/agent/
├── api/v2/
│   ├── router.py              # 挂载 skills-mgmt 路由
│   └── schemas.py             # 文件树、读写、上传响应
├── service/
│   └── skill_files_service.py # FS CRUD、zip 解压、校验
└── infrastructure/
    └── skill_loader.py        # 新增 invalidate_skill_cache()
```

新增依赖注入：`require_tenant_owner_or_admin(workspace_id)`（`app/core/api/deps.py`）：

1. `require_workspace_member`
2. 查 `Workspace.tenant_id`
3. 查 `TenantMembership.role ∈ {owner, admin}`

新增领域服务：`find_tenant_role_for_user(session, user_id, tenant_id)`（`identity/services.py`）。

### 3.2 API 端点

前缀：`/workspaces/{workspace_id}/agent/v2/skills-mgmt/`  
所有端点均需 `require_tenant_owner_or_admin`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/registry` | 一级列表：各技能文件夹 + INDEX 摘要 |
| GET | `/{skill_id}/tree` | 技能内递归文件树 |
| GET | `/files?path=` | 读文本文件（path 相对 skills 根） |
| PUT | `/files?path=` | 保存 `.md`/`.py`/`.json` → 触发缓存失效 |
| POST | `/upload` | 上传 zip 技能包 |
| POST | `/files/upload?path=` | 向指定目录上传单文件 |
| GET | `/files/download?path=` | 下载任意文件 |
| DELETE | `/files?path=` | 删除文件或目录 |
| DELETE | `/{skill_id}` | 删除整个技能目录 |

### 3.3 路径安全

- 所有 path 归一化后必须在 `skills_root()` 内。
- 拒绝 `..`、绝对路径、符号链接逃逸。
- `skill_id` 仅允许 `[a-z][a-z0-9_]*`（小写字母开头；与 `_normalize_skill_id` 一致）；保留字 `registry` 不可用。
- 文本读写单文件上限 **2MB**。

### 3.4 zip 上传流程

1. 保存 zip 到临时目录 `skills/.tmp/{uuid}/`。
2. 解压并检查根级条目：**恰好 1 个目录**（不允许多个散落根文件）。
3. 目录名 = `skill_id`；若 `skills/{skill_id}/` 已存在 → 409 `skills.duplicate`。
4. 目录内必须含 `SKILL.md`；否则 400 `skills.zip_missing_skill_md`。
5. 过滤跳过 `__pycache__/`、`.pyc`。
6. `shutil.move` 到 `skills/{skill_id}/`；失败清理临时目录。
7. 调用 `invalidate_skill_cache(skill_id)`。

### 3.5 缓存失效

`skill_loader.py` 新增：

```python
def invalidate_skill_cache(skill_id: str | None = None) -> None:
    list_indexed_skills.cache_clear()
    if skill_id:
        importlib.invalidate_caches()
        # 移除 sys.modules 中 app.agent.skills.{skill_id}.tools
```

以下写操作后均调用：

- 写 `INDEX.md`
- 写任意 `SKILL.md` / `tools.py`
- 上传/删除 skill 目录

响应可选字段 `cache_reloaded: bool`；若刷新失败，文件仍保存成功，前端 toast 警告。

### 3.6 错误码

| 错误码 | 场景 | HTTP |
|--------|------|------|
| `skills.forbidden` | 非租户 owner/admin | 403 |
| `skills.path_invalid` | 路径穿越、非法 skill_id | 400 |
| `skills.not_found` | 文件/目录不存在 | 404 |
| `skills.duplicate` | zip skill_id 已存在 | 409 |
| `skills.zip_invalid` | zip 根目录不是单个文件夹 | 400 |
| `skills.zip_missing_skill_md` | zip 内无 SKILL.md | 400 |
| `skills.not_editable` | 对非 md/py/json 发 PUT | 400 |
| `skills.json_invalid` | JSON 语法错误 | 400 |
| `skills.delete_failed` | IO 失败 | 500 |

---

## 4. 前端设计

### 4.1 路由

| 路由 | 组件 |
|------|------|
| `/app/agents/skills` | `AgentSkillsListPage` |
| `/app/agents/skills/:skillId` | `AgentSkillDetailPage` |
| `/app/agents/skills/registry` | `AgentSkillRegistryPage`（编辑 INDEX.md） |

`INDEX.md` 在一级列表顶部单独一行「技能注册表」，点击进入 `registry` 静态路由（须在 `:skillId` 动态路由之前注册）。

### 4.2 一级页面：技能列表

- Ant Design `Table` + 分页（`DEFAULT_PAGE_SIZE = 10`）。
- 顶栏「上传技能包」：`Upload` → `POST /skills-mgmt/upload`。
- 列：技能 ID、描述（INDEX 摘要）、文件数、操作（进入 / 删除）。
- 删除整技能：`Popconfirm` → `DELETE /skills-mgmt/{skill_id}`。
- 非租户 owner/admin：隐藏写操作；后端 403 兜底。

### 4.3 二级页面：技能详情

- 左：`Tree` 展示 `/tree` 递归结构。
- 右：按扩展名切换编辑器或二进制操作面板。
- 顶栏：面包屑、保存 / 下载 / 删除。
- 未保存离开：`beforeunload` + 路由拦截。
- 滚动条：`minerva-scrollbar-styled`。

### 4.4 编辑器

新增依赖 `@monaco-editor/react`（Vite 按需加载）：

| 扩展名 | Monaco language | 特性 |
|--------|-----------------|------|
| `.py` | `python` | 语法高亮、缩进 |
| `.md` | `markdown` | 语法高亮；可选预览（`react-markdown`） |
| `.json` | `json` | 语法高亮；保存前 `JSON.parse` 校验 |

非 md/py/json：显示文件信息 + 下载 / 删除 / 上传替换。

### 4.5 API 客户端

`frontend/src/api/agentSkillsMgmt.ts`：

- `listSkillRegistry` / `getSkillTree` / `readSkillFile` / `writeSkillFile`
- `uploadSkillPackage` / `uploadSkillFile` / `downloadSkillFile`
- `deleteSkillPath` / `deleteSkill`

### 4.6 权限 UI

- JWT 新增 `trole` claim（tenant role）；`AuthContext` 暴露 `canManageTenantSkills`。
- 旧 token 无 `trole`：提示重新登录；后端 DB 校验兜底。

### 4.7 文件结构

```
frontend/src/features/agent/skills/
├── AgentSkillsListPage.tsx
├── AgentSkillDetailPage.tsx
├── AgentSkillRegistryPage.tsx
├── components/
│   ├── SkillFileTree.tsx
│   ├── SkillFileEditor.tsx
│   └── SkillBinaryFilePanel.tsx
└── AgentSkillsPage.css
```

---

## 5. 边界情况

| 场景 | 处理 |
|------|------|
| 删除 `general` 等内置技能 | 允许；`default_skill_id()` 回退 |
| INDEX.md 清空 | fallback 扫描含 SKILL.md 的子目录 |
| tools.py 语法错误 | 允许保存；运行时 register_tools 失败已有 log |
| 并发编辑 | 后写覆盖，不做乐观锁 |
| zip 含 __pycache__ | 解压时过滤 |
| 符号链接 | 拒绝 |

---

## 6. 测试计划

**后端单元测试**（`backend/tests/agent/test_skill_files_service.py`）：

- 路径校验拒绝穿越
- zip：多根文件 / 单文件夹 / 重名 / 缺 SKILL.md
- 缓存失效后 list_indexed_skills 更新
- member 403；tenant admin 200

**集成测试**：upload → list → read → write → delete 全流程。

**前端**：手动验证两级导航、Monaco language 切换、JSON 校验、Popconfirm 删除、权限按钮隐藏。

---

## 7. 文档回填

实现完成后更新：

- `docs/agent-module-design.md` §1.4：移除「用户上传自定义 Skill 包」非目标条目，改为指向本 spec。

---

## 8. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 管理范围 | 全局 `backend/app/agent/skills/` | 用户明确 A |
| 权限 | 租户 owner + admin | 与工作区写操作惯例一致 |
| 内置技能 | 完全开放编辑/删除 | 用户明确 A |
| 上传 | zip 单根文件夹 + 重名校验 | 用户明确 |
| 生效时机 | 保存后立即清缓存 | 用户明确 |
| 可编辑格式 | md / py / json | 用户明确 |
| UI 布局 | 两级导航 | 用户明确 B |
| 编辑器 | Monaco | 项目尚无代码编辑器，Monaco 成熟 |
