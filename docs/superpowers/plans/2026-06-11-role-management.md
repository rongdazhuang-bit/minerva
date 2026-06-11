# 角色管理（sys_role + sys_role_menu）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现按 workspace 隔离的角色 CRUD、角色-菜单权限配置（Drawer + M/C/F 树），以及设置页「角色管理」列表 UI。

**Architecture:** 后端按 `app/sys/celery` 分层（workspace 路由 + `require_workspace_member` 读 / `require_workspace_owner_or_admin` 写）；`sys_role_menu.menu_id` 引用全局 `sys_menu`；菜单权限树通过 `GET .../roles/menu-tree` 内部复用 `menu_service.list_menu_tree`；前端 `RolesPage` 对齐 Celery 分页列表 + `MenuFormDrawer` 风格 Drawer；`SYS_ROLES` 字典仅用于筛选与展示映射。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, PostgreSQL, pytest, React 18, Ant Design, TypeScript, react-i18next, @tanstack/react-query（列表缓存）。

**设计文档：** `docs/superpowers/specs/2026-06-11-role-management-design.md`

---

## File Structure

### Backend（新建）

| 文件 | 职责 |
|------|------|
| `backend/sql/tables/sys_role.sql` | `sys_role` 建表 DDL |
| `backend/sql/tables/sys_role_menu.sql` | `sys_role_menu` 建表 DDL |
| `backend/sql/patches/2026-06-11-sys-role.sql` | 已有库增量建表 |
| `backend/app/sys/role/domain/db/models.py` | `SysRole`、`SysRoleMenu` ORM |
| `backend/app/sys/role/infrastructure/repository.py` | 按 workspace 查询/写入/删关联 |
| `backend/app/sys/role/service/role_service.py` | 校验、唯一性、menu_ids 替换、删除 |
| `backend/app/sys/role/api/schemas.py` | Pydantic |
| `backend/app/sys/role/api/router.py` | 6 个端点 |
| `backend/tests/test_role_service.py` | service 单元测试 |
| `backend/tests/test_role_api.py` | API 鉴权/路由集成测试 |

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/sql/schema_postgresql.sql` | 追加 `sys_role`、`sys_role_menu` |
| `backend/app/core/infrastructure/db/bootstrap.py` | 注册 role ORM |
| `backend/app/core/api/router.py` | `include_router(roles_router)` |

### Frontend（新建）

| 文件 | 职责 |
|------|------|
| `frontend/src/api/roles.ts` | API 客户端与类型 |
| `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | 新增/编辑 Drawer + 菜单 Checkbox Tree |
| `frontend/src/features/settings/roles/RolesPage.css` | 表格滚动（如需） |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/features/settings/roles/RolesPage.tsx` | 完整列表页 |
| `frontend/src/features/settings/users/UsersPage.tsx` | 占位文案更新 |
| `frontend/src/i18n/locales/zh-CN.json` | `roles.*` 文案 |
| `frontend/src/i18n/locales/en.json` | `roles.*` 文案 |

---

### Task 1: SQL 建表

**Files:**
- Create: `backend/sql/tables/sys_role.sql`
- Create: `backend/sql/tables/sys_role_menu.sql`
- Create: `backend/sql/patches/2026-06-11-sys-role.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 编写 `backend/sql/tables/sys_role.sql`**

```sql
CREATE TABLE IF NOT EXISTS public.sys_role (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  role_name     VARCHAR(64)  NOT NULL,
  role_key      VARCHAR(64)  NOT NULL,
  role_sort     INT          NOT NULL DEFAULT 0,
  status        BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_workspace_role_key
  ON public.sys_role (workspace_id, role_key);
CREATE INDEX IF NOT EXISTS ix_sys_role_workspace_id ON public.sys_role (workspace_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_role_sort ON public.sys_role (role_sort);
COMMENT ON TABLE public.sys_role IS 'Workspace-scoped RBAC role';
COMMENT ON COLUMN public.sys_role.role_key IS 'Permission key; unique per workspace';
```

- [ ] **Step 2: 编写 `backend/sql/tables/sys_role_menu.sql`**

```sql
CREATE TABLE IF NOT EXISTS public.sys_role_menu (
  id       UUID NOT NULL,
  role_id  UUID NOT NULL,
  menu_id  UUID NOT NULL,
  PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_role_menu_role_menu
  ON public.sys_role_menu (role_id, menu_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_role_id ON public.sys_role_menu (role_id);
CREATE INDEX IF NOT EXISTS ix_sys_role_menu_menu_id ON public.sys_role_menu (menu_id);
COMMENT ON TABLE public.sys_role_menu IS 'Role to global sys_menu mapping (app-enforced)';
```

- [ ] **Step 3: 编写 patch 并合并进 `schema_postgresql.sql`**

`backend/sql/patches/2026-06-11-sys-role.sql` 内容：

```sql
\i ../tables/sys_role.sql
\i ../tables/sys_role_menu.sql
```

（若项目 patch 惯例为内联 SQL，则直接 `\i` 等价的两段 CREATE；与 `2026-06-10-sys-menu.sql` 风格保持一致。）

- [ ] **Step 4: Commit**

```bash
git add backend/sql/tables/sys_role.sql backend/sql/tables/sys_role_menu.sql backend/sql/patches/2026-06-11-sys-role.sql backend/sql/schema_postgresql.sql
git commit -m "feat(role): add sys_role and sys_role_menu schema"
```

---

### Task 2: ORM 与 bootstrap

**Files:**
- Create: `backend/app/sys/role/__init__.py`
- Create: `backend/app/sys/role/domain/__init__.py`
- Create: `backend/app/sys/role/domain/db/__init__.py`
- Create: `backend/app/sys/role/domain/db/models.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`

- [ ] **Step 1: 编写 ORM `models.py`**

```python
"""SQLAlchemy models for workspace-scoped roles and role-menu links."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysRole(Base):
    """RBAC role row scoped to one workspace."""

    __tablename__ = "sys_role"
    __table_args__ = (
        UniqueConstraint("workspace_id", "role_key", name="uq_sys_role_workspace_role_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role_key: Mapped[str] = mapped_column(String(64), nullable=False)
    role_sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SysRoleMenu(Base):
    """Maps a workspace role to a global sys_menu id (app-enforced)."""

    __tablename__ = "sys_role_menu"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_id", name="uq_sys_role_menu_role_menu"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    menu_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
```

- [ ] **Step 2: 在 `bootstrap.py` 的 `_import_models()` 追加**

```python
import app.sys.role.domain.db.models  # noqa: F401
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/sys/role backend/app/core/infrastructure/db/bootstrap.py
git commit -m "feat(role): add SysRole ORM and bootstrap registration"
```

---

### Task 3: Repository 层

**Files:**
- Create: `backend/app/sys/role/infrastructure/__init__.py`
- Create: `backend/app/sys/role/infrastructure/repository.py`

- [ ] **Step 1: 实现 repository**

需包含以下函数（均带 docstring，见 code-comments skill）：

```python
async def list_roles_page(
    session, *, workspace_id, role_name, status, role_key, offset, limit
) -> tuple[list[SysRole], int]

async def get_role_by_id(session, role_id) -> SysRole | None

async def get_role_for_workspace(session, *, workspace_id, role_id) -> SysRole | None

async def add_role(session, row: SysRole) -> None

async def delete_role(session, role_id) -> None

async def list_menu_ids_for_role(session, role_id) -> list[uuid.UUID]

async def replace_role_menus(session, *, role_id, menu_ids: list[uuid.UUID]) -> None
# 实现：delete all by role_id，再 bulk insert

async def delete_role_menus(session, role_id) -> None
```

列表 count + 分页查询同一 workspace；`role_name` 用 `ilike '%..%'`；`role_key` 精确匹配。

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/role/infrastructure/
git commit -m "feat(role): add role repository"
```

---

### Task 4: Role service（TDD）

**Files:**
- Create: `backend/app/sys/role/service/__init__.py`
- Create: `backend/app/sys/role/service/role_service.py`
- Create: `backend/tests/test_role_service.py`

- [ ] **Step 1: 写失败测试 `test_role_service.py`**

覆盖：

```python
@pytest.mark.asyncio
async def test_create_role_rejects_invalid_menu_ids(monkeypatch):
    # menu_service 或 menu repo 返回已知 menu ids 集合
    # menu_ids 含未知 id -> AppError role.invalid_menu_ids

@pytest.mark.asyncio
async def test_create_role_conflict_on_duplicate_role_key(monkeypatch):
    # IntegrityError / unique violation -> AppError role.conflict 409

@pytest.mark.asyncio
async def test_get_role_wrong_workspace_returns_not_found(monkeypatch):
    # role.workspace_id != path workspace -> AppError role.not_found 404

@pytest.mark.asyncio
async def test_delete_role_removes_menus_first(monkeypatch):
    # 断言先 delete_role_menus 再 delete_role
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd backend && pytest tests/test_role_service.py -v`  
Expected: FAIL（模块/函数不存在）

- [ ] **Step 3: 实现 `role_service.py` 核心函数**

```python
async def list_roles_page(...) -> RoleListPageOut  # 组装分页

async def get_role_detail(session, *, workspace_id, role_id) -> RoleDetailOut
    # 404 if not found or workspace mismatch

async def create_role(session, *, workspace_id, data) -> SysRole
    # validate menu_ids via menu repo list_all ids set
    # insert role + replace_role_menus
    # catch IntegrityError on uq_sys_role_workspace_role_key -> role.conflict

async def update_role(session, *, workspace_id, role_id, patch) -> SysRole
    # 若 patch 含 menu_ids 则 replace

async def delete_role(session, *, workspace_id, role_id) -> None
    # 404 check -> delete_role_menus -> delete_role

async def list_menu_tree_for_role_assignment(session) -> list[SysMenuNodeOut]
    # from app.sys.menu.service.menu_service import list_menu_tree
    # return await list_menu_tree(session)  # 无 filter，全 M/C/F
```

`_utc_now()` 更新 `update_at`；创建时写 `create_at`/`update_at`。

- [ ] **Step 4: 运行测试 PASS**

Run: `cd backend && pytest tests/test_role_service.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/role/service/ backend/tests/test_role_service.py
git commit -m "feat(role): add role service with validation tests"
```

---

### Task 5: API schemas 与 router

**Files:**
- Create: `backend/app/sys/role/api/__init__.py`
- Create: `backend/app/sys/role/api/schemas.py`
- Create: `backend/app/sys/role/api/router.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: schemas.py**

```python
class SysRoleCreateIn(BaseModel):
    role_name: str = Field(min_length=1, max_length=64)
    role_key: str = Field(min_length=1, max_length=64)
    role_sort: int = 0
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)
    menu_ids: list[uuid.UUID] = Field(default_factory=list)

class SysRolePatchIn(BaseModel):
    role_name: str | None = Field(default=None, min_length=1, max_length=64)
    role_key: str | None = Field(default=None, min_length=1, max_length=64)
    role_sort: int | None = None
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)
    menu_ids: list[uuid.UUID] | None = None

class SysRoleListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    role_name: str
    role_key: str
    role_sort: int
    status: bool
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None

class SysRoleDetailOut(SysRoleListItemOut):
    menu_ids: list[uuid.UUID]

class SysRoleListPageOut(BaseModel):
    items: list[SysRoleListItemOut]
    total: int
    page: int
    page_size: int
```

`menu-tree` 响应复用 `app.sys.menu.api.schemas.SysMenuNodeOut`。

- [ ] **Step 2: router.py**

前缀 `/workspaces/{workspace_id}/roles`；6 个端点按 spec §3.2；读用 `require_workspace_member`，写用 `require_workspace_owner_or_admin`。

`menu-tree` 路由**必须**注册在 `/{role_id}` **之前**：

```python
@router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree(..., _member: uuid.UUID = Depends(require_workspace_member)):
    return await svc.list_menu_tree_for_role_assignment(session)
```

- [ ] **Step 3: 注册路由**

`backend/app/core/api/router.py`：

```python
from app.sys.role.api.router import router as roles_router
...
api.include_router(roles_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/role/api/ backend/app/core/api/router.py
git commit -m "feat(role): add workspace-scoped roles API routes"
```

---

### Task 6: API 集成测试

**Files:**
- Create: `backend/tests/test_role_api.py`

- [ ] **Step 1: 编写测试（monkeypatch service，不测 DB）**

```python
WS_A = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000r1")

def test_list_forbidden_for_non_member(...):
    # require_workspace_member -> 403

def test_create_forbidden_for_member(...):
    # member GET ok, POST -> 403

def test_owner_create_ok(...):
    # override owner/admin -> 201

def test_get_role_cross_workspace_404(...):
    # service raises role.not_found -> 404
```

依赖 override 模式对齐 `test_menu_api.py` / `test_dataset_api.py`。

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_role_api.py tests/test_role_service.py -v`  
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_role_api.py
git commit -m "test(role): add API auth and routing tests"
```

---

### Task 7: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/roles.ts`

- [ ] **Step 1: 实现 API 函数**

```typescript
import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'

export type SysRoleListItem = {
  id: string
  workspace_id: string
  role_name: string
  role_key: string
  role_sort: number
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type SysRoleDetail = SysRoleListItem & { menu_ids: string[] }

export type SysRoleListPage = {
  items: SysRoleListItem[]
  total: number
  page: number
  page_size: number
}

export type SysRoleListParams = {
  role_name?: string
  status?: boolean
  role_key?: string
  page?: number
  page_size?: number
}

export type SysRoleCreateBody = {
  role_name: string
  role_key: string
  role_sort?: number
  status?: boolean
  remark?: string | null
  menu_ids?: string[]
}

export type SysRolePatchBody = Partial<SysRoleCreateBody>

export function listRoles(workspaceId: string, params: SysRoleListParams = {}) {
  const q = new URLSearchParams()
  // append params...
  return apiJson<SysRoleListPage>(`/workspaces/${workspaceId}/roles?${q}`)
}

export function listRoleMenuTree(workspaceId: string) {
  return apiJson<SysMenuNode[]>(`/workspaces/${workspaceId}/roles/menu-tree`)
}

export function getRole(workspaceId: string, roleId: string) {
  return apiJson<SysRoleDetail>(`/workspaces/${workspaceId}/roles/${roleId}`)
}

export function createRole(workspaceId: string, body: SysRoleCreateBody) { ... }
export function patchRole(workspaceId: string, roleId: string, body: SysRolePatchBody) { ... }
export function deleteRole(workspaceId: string, roleId: string) { ... }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/roles.ts
git commit -m "feat(role): add frontend roles API client"
```

---

### Task 8: RoleFormDrawer

**Files:**
- Create: `frontend/src/features/settings/roles/RoleFormDrawer.tsx`

- [ ] **Step 1: 实现 Drawer 组件**

要点：

- Props：`open`, `title`, `submitting`, `editingId`, `initial`, `menuTree`, `onClose`, `onSubmit`
- 表单字段：role_name, role_key, role_sort, status (Radio), remark (TextArea)
- **菜单权限**：
  - 顶部 Checkbox：`expandAll`, `selectAll`, `checkStrictly`（父子联动，默认 false 即联动开启 — Ant Design `checkStrictly={!linkParentChild}`）
  - `Tree` `checkable`；`treeData` 由 `menuTree` 递归构建；F 节点 title 附 `(perms)`
  - 控制栏：展开/折叠切换 `expandedKeys`；全选/全不选切换 `checkedKeys`
- `useEffect` 在 `open` 时 reset 表单与 checkedKeys（来自 `initial.menu_ids`）
- Input / Select 带 `allowClear`（code-comments 约定）；排序用 `InputNumber`
- 提交：`onSubmit({ ...values, menu_ids: checkedKeys })`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/settings/roles/RoleFormDrawer.tsx
git commit -m "feat(role): add RoleFormDrawer with menu permission tree"
```

---

### Task 9: RolesPage 列表页

**Files:**
- Modify: `frontend/src/features/settings/roles/RolesPage.tsx`
- Create: `frontend/src/features/settings/roles/RolesPage.css`（可选）
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 实现 RolesPage**

对齐 `CeleryPage` 模式：

- `useAuth()` → `workspaceId`, `isWorkspaceManager`
- `useQuery` 拉 `listRoles`；`page`/`pageSize`/`filters`
- 挂载时 `listAllDicts` + 找 `SYS_ROLES` → 构建筛选项与 `code→name` Map
- 无 `SYS_ROLES`：`message.warning(t('roles.sysRolesDictMissing'))` 一次（`useRef` 防重复）
- 列定义见 spec §4.1；权限字符列用 Map 展示
- **写操作**：仅 `isWorkspaceManager` 显示「新增」与行内修改/删除
- 删除 `Popconfirm`（非 Modal.confirm）
- Drawer：打开时 `listRoleMenuTree(workspaceId)`；编辑时 `getRole`
- 403：`Result status="403"`

**i18n 键示例（zh-CN）**：

```json
"roles.title": "角色管理",
"roles.add": "新增",
"roles.edit": "修改",
"roles.roleName": "角色名称",
"roles.roleKey": "权限字符",
"roles.roleSort": "角色顺序",
"roles.status": "状态",
"roles.statusNormal": "正常",
"roles.statusDisabled": "停用",
"roles.menuPermissions": "菜单权限",
"roles.expandCollapse": "展开/折叠",
"roles.selectAll": "全选/全不选",
"roles.parentChildLink": "父子联动",
"roles.remark": "备注",
"roles.deleteConfirmTitle": "确定删除角色「{{name}}」吗？",
"roles.deleteConfirmDesc": "删除后不可恢复。",
"roles.sysRolesDictMissing": "当前工作空间未配置 SYS_ROLES 字典，权限字符筛选项不可用。"
```

- [ ] **Step 2: 手动冒烟**

1. workspace owner/admin 新增角色并勾选菜单，保存后编辑回显  
2. member 登录仅可读列表  
3. `role_key` 重复报错  

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/roles/ frontend/src/i18n/locales/
git commit -m "feat(role): implement RolesPage with filters and drawer"
```

---

### Task 10: 后续占位与文档回填

**Files:**
- Modify: `frontend/src/features/settings/users/UsersPage.tsx`
- Modify: `docs/superpowers/specs/2026-06-11-role-management-design.md`

- [ ] **Step 1: 更新 UsersPage 占位文案**

zh-CN：`placeholders.userMgmt` → 「用户角色分配功能开发中。」（或新增专用键 `placeholders.userRoleAssign`）

- [ ] **Step 2: 回填 spec 状态**

`2026-06-11-role-management-design.md`：

- **状态** → `已实现（YYYY-MM-DD）`
- 追加 **§9 实现对照** 表格（ORM、API、前端文件、测试路径）

- [ ] **Step 3: 运行全量相关测试**

Run: `cd backend && pytest tests/test_role_service.py tests/test_role_api.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/settings/users/UsersPage.tsx docs/superpowers/specs/2026-06-11-role-management-design.md
git commit -m "docs(role): mark spec implemented and update user mgmt placeholder"
```

---

## Spec Coverage Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| workspace 隔离 `sys_role` | Task 1–2 |
| `sys_role_menu` 无 FK | Task 1, 4 |
| `/workspaces/{id}/roles` CRUD + 分页 | Task 5 |
| `menu-tree` 端点 | Task 5 |
| workspace 内 `role_key` 唯一 | Task 4 |
| 跨 workspace 404 | Task 4, 6 |
| member 读 / owner-admin 写 | Task 5, 6, 9 |
| SYS_ROLES 筛选与展示 | Task 9 |
| Drawer M/C/F + 三控件 | Task 8 |
| Popconfirm 删除 | Task 9 |
| B/C 占位 | Task 10 |
| 默认分页 10 | Task 5, 9 |

无 TBD/占位步骤。

---

## 执行选项

Plan 已保存至 `docs/superpowers/plans/2026-06-11-role-management.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间人工/Agent review，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间设检查点

你选哪种？
