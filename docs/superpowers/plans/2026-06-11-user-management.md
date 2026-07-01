# 用户管理（sys_user 扩展 + sys_user_role + UsersPage）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 workspace 级用户成员 CRUD、多 `sys_role` 分配、`SYS_DEPARTMENT` 部门树选、成员资格（owner/admin/member）、移出 workspace / 硬删账号，以及设置页「用户管理」完整 UI。

**Architecture:** 后端新建 `app/sys/user/` 分层（对齐 `app/sys/role`）；扩展 `identity.models.User` 与 SQL `sys_user`；新建 `sys_user_role`；列表通过 `sys_workspace_user` 关联查询；部门校验复用 `app/sys/dict` 的 `get_dict_by_code_for_workspace` + `get_item_in_dict`；登录路径增加 `status` 校验；前端 `UsersPage` / `UserFormDrawer` 对齐 `RolesPage` / `RoleFormDrawer`（§4.4 UI 规范）。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, PostgreSQL, pytest, React 18, Ant Design 6, TypeScript, react-i18next, @tanstack/react-query。

**设计文档：** `docs/superpowers/specs/2026-06-11-user-management-design.md`

> **状态：已实现（2026-06-11）。** 用户角色绑定已于 2026-07-01 迁移至 `sys_user_grant`（见 [unified-permission-gateway plan](./2026-07-01-unified-permission-gateway.md)）；下文 Task 1–2 中 `sys_user_role` 描述为历史记录，应用层不再引用。

---

## File Structure

### Backend（新建）

| 文件 | 职责 |
|------|------|
| `backend/sql/tables/sys_user_role.sql` | `sys_user_role` 建表 DDL |
| `backend/sql/patches/2026-06-11-sys-user-mgmt.sql` | ALTER `sys_user` + 建 `sys_user_role` |
| `backend/app/sys/user/__init__.py` | 包标记 |
| `backend/app/sys/user/domain/__init__.py` | 域包 |
| `backend/app/sys/user/domain/db/__init__.py` | ORM 包 |
| `backend/app/sys/user/domain/db/models.py` | `SysUserRole` ORM |
| `backend/app/sys/user/infrastructure/__init__.py` | 仓储包 |
| `backend/app/sys/user/infrastructure/repository.py` | 成员列表、角色关联、删除 |
| `backend/app/sys/user/service/__init__.py` | 服务包 |
| `backend/app/sys/user/service/user_service.py` | 校验、CRUD、硬删权限 |
| `backend/app/sys/user/api/__init__.py` | API 包 |
| `backend/app/sys/user/api/schemas.py` | Pydantic |
| `backend/app/sys/user/api/router.py` | 8 个端点 |
| `backend/tests/test_user_service.py` | service 单元测试 |
| `backend/tests/test_user_api.py` | API 鉴权/路由集成测试 |

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/sql/schema_postgresql.sql` | `sys_user` 新列 + `sys_user_role` 表 |
| `backend/app/core/domain/identity/models.py` | `User` 增加 nickname/phone/status/remark/department_item_id/update_at |
| `backend/app/core/domain/identity/services.py` | `authenticate_user` 校验 `status`；可选辅助 `count_workspace_memberships` |
| `backend/app/core/infrastructure/db/bootstrap.py` | 注册 `SysUserRole` ORM |
| `backend/app/core/api/router.py` | `include_router(users_router)` |

### Frontend（新建）

| 文件 | 职责 |
|------|------|
| `frontend/src/api/users.ts` | API 客户端与类型 |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | 新增/编辑 Drawer |
| `frontend/src/features/settings/users/UsersPage.css` | 列表 flex + 表格滚动布局 |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/features/settings/users/UsersPage.tsx` | 完整列表页 |
| `frontend/src/i18n/locales/zh-CN.json` | `users.*` 文案 |
| `frontend/src/i18n/locales/en.json` | `users.*` 文案 |

### Docs（修改）

| 文件 | 变更 |
|------|------|
| `docs/superpowers/specs/2026-06-11-user-management-design.md` | 状态 → 已实现；实现对照表 |
| `docs/superpowers/specs/2026-06-11-role-management-design.md` | §5 回填：`sys_user_role` 已实现 |

---

### Task 1: SQL 迁移

**Files:**
- Create: `backend/sql/tables/sys_user_role.sql`
- Create: `backend/sql/patches/2026-06-11-sys-user-mgmt.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 编写 `backend/sql/tables/sys_user_role.sql`**

```sql
CREATE TABLE IF NOT EXISTS public.sys_user_role (
  id       UUID NOT NULL,
  user_id  UUID NOT NULL,
  role_id  UUID NOT NULL,
  CONSTRAINT sys_user_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_role_user_role
  ON public.sys_user_role (user_id, role_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_user_id ON public.sys_user_role (user_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_role_id ON public.sys_user_role (role_id);
COMMENT ON TABLE public.sys_user_role IS 'User to workspace sys_role mapping (app-enforced)';
```

- [ ] **Step 2: 编写 `backend/sql/patches/2026-06-11-sys-user-mgmt.sql`**

```sql
-- sys_user 档案扩展
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS nickname VARCHAR(64);
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS remark VARCHAR(500);
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS department_item_id UUID;
ALTER TABLE public.sys_user ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ;

UPDATE public.sys_user
SET nickname = split_part(email, '@', 1)
WHERE nickname IS NULL;

ALTER TABLE public.sys_user ALTER COLUMN nickname SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_phone
  ON public.sys_user (phone) WHERE phone IS NOT NULL;

COMMENT ON COLUMN public.sys_user.nickname IS 'Display name';
COMMENT ON COLUMN public.sys_user.phone IS 'Optional; globally unique when set';
COMMENT ON COLUMN public.sys_user.status IS 'true=active false=cannot login';
COMMENT ON COLUMN public.sys_user.department_item_id IS 'Logical ref sys_dict_item.id (SYS_DEPARTMENT)';

-- sys_user_role
CREATE TABLE IF NOT EXISTS public.sys_user_role (
  id       UUID NOT NULL,
  user_id  UUID NOT NULL,
  role_id  UUID NOT NULL,
  CONSTRAINT sys_user_role_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_user_role_user_role
  ON public.sys_user_role (user_id, role_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_user_id ON public.sys_user_role (user_id);
CREATE INDEX IF NOT EXISTS ix_sys_user_role_role_id ON public.sys_user_role (role_id);
```

- [ ] **Step 3: 合并进 `backend/sql/schema_postgresql.sql`**

在 `sys_user` CREATE 块内直接包含新列（新装库一次到位）；文件末尾追加 `\i` 等价内联的 `sys_user_role` 定义（与 `sys_role` 段落风格一致）。

- [ ] **Step 4: Commit**

```bash
git add backend/sql/tables/sys_user_role.sql backend/sql/patches/2026-06-11-sys-user-mgmt.sql backend/sql/schema_postgresql.sql
git commit -m "feat(user): add sys_user profile columns and sys_user_role schema"
```

---

### Task 2: ORM 模型

**Files:**
- Modify: `backend/app/core/domain/identity/models.py`
- Create: `backend/app/sys/user/domain/db/models.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`

- [ ] **Step 1: 扩展 `User` ORM**

在 `User` 类增加（`created_at` 之后）：

```python
nickname: Mapped[str] = mapped_column(String(64), nullable=False)
phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
status: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default=sa.true()
)
remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
department_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True), nullable=True
)
update_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

更新类 docstring 说明档案字段。

- [ ] **Step 2: 新建 `SysUserRole`**

```python
"""ORM for user-to-role assignments."""

class SysUserRole(Base):
    """Join row tying a user to a workspace-scoped sys_role."""

    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_sys_user_role_user_role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
```

- [ ] **Step 3: bootstrap 注册**

```python
import app.sys.user.domain.db.models  # noqa: F401
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/domain/identity/models.py backend/app/sys/user/ backend/app/core/infrastructure/db/bootstrap.py
git commit -m "feat(user): extend User ORM and add SysUserRole model"
```

---

### Task 3: Repository 层

**Files:**
- Create: `backend/app/sys/user/infrastructure/repository.py`

- [ ] **Step 1: 实现 repository 函数**

```python
async def count_workspace_members_for_workspace(
    session, *, workspace_id, email, nickname, phone, status, membership_role, role_id
) -> int

async def list_workspace_members_page(
    session, *, workspace_id, filters..., offset, limit
) -> list[tuple[User, WorkspaceMembership]]
# JOIN sys_user + sys_workspace_user WHERE workspace_id=?
# 可选 JOIN sys_user_role 过滤 role_id
# ORDER BY sys_user.created_at DESC

async def get_member_user(
    session, *, workspace_id, user_id
) -> tuple[User, WorkspaceMembership] | None

async def list_role_ids_for_user_in_workspace(
    session, *, workspace_id, user_id
) -> list[uuid.UUID]
# SELECT role_id FROM sys_user_role JOIN sys_role ON ... WHERE user_id AND workspace_id

async def replace_user_roles_in_workspace(
    session, *, workspace_id, user_id, role_ids: list[uuid.UUID]
) -> None
# DELETE sys_user_role for roles in workspace, then bulk insert

async def delete_user_roles_in_workspace(session, *, workspace_id, user_id) -> None

async def count_all_memberships_for_user(session, *, user_id) -> int

async def delete_all_user_roles(session, *, user_id) -> None

async def delete_all_memberships(session, *, user_id) -> None

async def delete_refresh_tokens(session, *, user_id) -> None

async def delete_user_row(session, *, user_id) -> None

async def get_user_by_email(session, *, email: str) -> User | None

async def get_user_by_phone(session, *, phone: str) -> User | None
```

`email` 查询用 `lower(email)` 与注册逻辑一致。

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/user/infrastructure/
git commit -m "feat(user): add user repository queries"
```

---

### Task 4: User service（TDD）

**Files:**
- Create: `backend/app/sys/user/service/user_service.py`
- Create: `backend/tests/test_user_service.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_create_user_rejects_existing_email(monkeypatch):
    # get_user_by_email 返回已有用户 -> AppError user.email_taken 409

@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_phone(monkeypatch):
    # phone 非空且已占用 -> user.phone_taken 409

@pytest.mark.asyncio
async def test_create_user_rejects_invalid_department(monkeypatch):
    # department_item_id 不在 SYS_DEPARTMENT -> user.department_invalid 400

@pytest.mark.asyncio
async def test_create_user_rejects_invalid_role_ids(monkeypatch):
    # role_id 不属于 workspace -> user.role_invalid 400

@pytest.mark.asyncio
async def test_remove_membership_clears_workspace_roles_only(monkeypatch):
    # 仅删当前 workspace 的 sys_user_role + membership

@pytest.mark.asyncio
async def test_hard_delete_forbidden_multi_workspace(monkeypatch):
    # 非超管 + membership count > 1 -> user.delete_forbidden 403

@pytest.mark.asyncio
async def test_hard_delete_allowed_sole_workspace_for_admin(monkeypatch):
    # 非超管 + count==1 -> 成功删除 users
```

- [ ] **Step 2: 运行确认 FAIL**

Run: `cd backend && pytest tests/test_user_service.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `user_service.py`**

核心函数：

```python
DEPARTMENT_DICT_CODE = "SYS_DEPARTMENT"

async def _validate_department_item(
    session, *, workspace_id, department_item_id: uuid.UUID | None
) -> None:
    if department_item_id is None:
        return
    d = await dict_repo.get_dict_by_code_for_workspace(
        session, workspace_id=workspace_id, dict_code=DEPARTMENT_DICT_CODE
    )
    if d is None:
        raise AppError("user.department_invalid", "Department dict not found", 400)
    item = await dict_repo.get_item_in_dict(
        session, dict_uuid=d.id, item_id=department_item_id
    )
    if item is None:
        raise AppError("user.department_invalid", "Invalid department item", 400)

async def _validate_role_ids(
    session, *, workspace_id, role_ids: list[uuid.UUID]
) -> None:
    # 每个 id 须 get_role_for_workspace 且 status=True

async def _compute_can_hard_delete(
    session, *, actor_user_id, workspace_id, target_user_id, is_super_admin: bool
) -> bool:
    if is_super_admin:
        return True
    n = await repo.count_all_memberships_for_user(session, user_id=target_user_id)
    if n != 1:
        return False
    member = await repo.get_member_user(session, workspace_id=workspace_id, user_id=target_user_id)
    return member is not None

async def list_users_page(...) -> tuple[list[UserListRow], int]
async def get_user_detail(...) -> UserDetailOut
async def create_user(...) -> UserDetailOut
async def update_user(...) -> UserDetailOut
async def remove_membership(...) -> None
async def delete_user_account(session, *, workspace_id, user_id, actor: User) -> None
async def list_department_tree(session, *, workspace_id) -> list[SysDictItemNodeOut]
async def list_assignable_roles(session, *, workspace_id) -> list[RoleMetaOut]
```

`create_user` 流程：
1. `email = email.strip().lower()`
2. 校验 password ≥ 8
3. 邮箱/手机唯一
4. department / role_ids 校验
5. `User(..., password_hash=hash_password(password), nickname=...)`
6. `WorkspaceMembership(user_id, workspace_id, role=membership_role)`
7. `replace_user_roles_in_workspace`
8. commit；`IntegrityError` 23505 → `user.email_taken` / `user.phone_taken`

`update_user`：`password` 非空才 `hash_password`；`role_ids` 提供则全量替换。

- [ ] **Step 4: 运行测试 PASS**

Run: `cd backend && pytest tests/test_user_service.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/user/service/ backend/tests/test_user_service.py
git commit -m "feat(user): add user service with validation tests"
```

---

### Task 5: 登录 status 校验

**Files:**
- Modify: `backend/app/core/domain/identity/services.py`
- Create or extend: `backend/tests/test_auth_status.py`（或并入已有 auth 测试）

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_authenticate_user_rejects_disabled_status():
    # user.status=False -> authenticate_user returns None
```

- [ ] **Step 2: 修改 `authenticate_user`**

在密码校验通过后、查 workspace 之前：

```python
if not user.status:
    return None
```

- [ ] **Step 3: 运行测试 PASS**

Run: `cd backend && pytest tests/test_auth_status.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/domain/identity/services.py backend/tests/test_auth_status.py
git commit -m "feat(user): block login for disabled users"
```

---

### Task 6: API schemas 与 router

**Files:**
- Create: `backend/app/sys/user/api/schemas.py`
- Create: `backend/app/sys/user/api/router.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: schemas.py**

```python
class SysUserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)
    membership_role: MembershipRole  # 或 Literal['owner','admin','member']
    department_item_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = Field(default_factory=list)

class SysUserPatchIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    status: bool | None = None
    remark: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    membership_role: MembershipRole | None = None
    department_item_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] | None = None

class SysUserListItemOut(BaseModel):
    id: uuid.UUID
    email: str
    nickname: str
    phone: str | None
    status: bool
    remark: str | None
    department_item_id: uuid.UUID | None
    department_name: str | None
    membership_role: str
    role_ids: list[uuid.UUID]
    role_names: list[str]
    created_at: datetime
    update_at: datetime | None
    can_hard_delete: bool

class SysUserListPageOut(BaseModel):
    items: list[SysUserListItemOut]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: router.py 端点**

前缀 `/workspaces/{workspace_id}/users`：

| 路由 | 依赖 |
|------|------|
| GET `` | `require_workspace_member` |
| GET `/{user_id}` | member |
| POST `` | `require_workspace_owner_or_admin` |
| PATCH `/{user_id}` | owner/admin |
| DELETE `/{user_id}/membership` | owner/admin |
| DELETE `/{user_id}` | owner/admin（service 内硬删权限） |
| GET `/meta/departments` | member |
| GET `/meta/roles` | member |

硬删 handler 注入 `get_current_user`，调用 `is_super_admin_user` 传入 service。

- [ ] **Step 3: 挂载路由**

```python
from app.sys.user.api.router import router as users_router
api.include_router(users_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/user/api/ backend/app/core/api/router.py
git commit -m "feat(user): add workspace users API routes"
```

---

### Task 7: API 集成测试

**Files:**
- Create: `backend/tests/test_user_api.py`

- [ ] **Step 1: 鉴权测试（对齐 test_role_api.py）**

```python
def test_list_forbidden_for_non_member():
    assert 403 auth.forbidden

def test_create_forbidden_for_member_only(member_client):
    assert 403

def test_member_list_ok(member_client, monkeypatch):
    # mock list_users_page 返回空分页 200
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_user_api.py -v`  
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_user_api.py
git commit -m "test(user): add users API auth integration tests"
```

---

### Task 8: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/users.ts`

- [ ] **Step 1: 实现 types + 函数**

对齐 `frontend/src/api/roles.ts` 风格：

```typescript
export type SysUserListItem = { ... can_hard_delete: boolean }
export type SysUserDetail = SysUserListItem
export type SysUserListParams = { email?, nickname?, phone?, status?, membership_role?, role_id?, page?, page_size? }
export type SysUserCreateBody = { email, password, nickname, phone?, status?, remark?, membership_role, department_item_id?, role_ids? }
export type SysUserPatchBody = Partial<Omit<SysUserCreateBody, 'email'>> & { password?: string }

export function listUsers(workspaceId, params)
export function getUser(workspaceId, userId)
export function createUser(workspaceId, body)
export function patchUser(workspaceId, userId, body)
export function removeUserMembership(workspaceId, userId)
export function deleteUserAccount(workspaceId, userId)
export function listUserDepartmentTree(workspaceId)
export function listUserAssignableRoles(workspaceId)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/users.ts
git commit -m "feat(user): add frontend users API client"
```

---

### Task 9: UserFormDrawer

**Files:**
- Create: `frontend/src/features/settings/users/UserFormDrawer.tsx`

- [ ] **Step 1: 实现 Drawer**

对齐 `RoleFormDrawer`：

- `width={520}`、`destroyOnClose`
- `classNames={{ body: 'minerva-scrollbar-styled' }}`
- 字段：email（编辑 disabled）、password、nickname、phone、status Radio、membership_role Select、department TreeSelect（`allowClear`）、roles Select multiple、`remark` TextArea
- 打开时并行请求 `listUserDepartmentTree` + `listUserAssignableRoles`
- 无部门字典时 `Alert type="info"`
- TreeSelect `treeData` 复用 `DictionaryPage` 的 `buildItemTreeData` 逻辑（可抽本地 helper 或复制最小函数）
- Props: `open`, `title`, `submitting`, `mode: 'create'|'edit'`, `initial`, `onClose`, `onSubmit`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/settings/users/UserFormDrawer.tsx
git commit -m "feat(user): add user form drawer"
```

---

### Task 10: UsersPage + CSS

**Files:**
- Create: `frontend/src/features/settings/users/UsersPage.css`
- Modify: `frontend/src/features/settings/users/UsersPage.tsx`

- [ ] **Step 1: CSS（复制 RolesPage 并改名）**

```css
.minerva-users-page { /* 同 minerva-roles-page */ }
.minerva-users-page__card { ... }
.minerva-users-page__header { ... }
.minerva-users-page__table-wrap { ... }
```

- [ ] **Step 2: UsersPage 列表**

对齐 `RolesPage.tsx`：

- `useAuth().workspaceId` + `isWorkspaceManager`
- `useQuery` + `DEFAULT_PAGE_SIZE`
- 筛选 Form inline + `allowClear`
- Table `className="minerva-card-table-scroll-ocr"`、`scroll={{ x: 1200 }}`
- 操作列：编辑；移出 `Popconfirm`；删除账号 `Popconfirm`（`can_hard_delete` 为 true 时显示）
- `UserFormDrawer` 集成 create/edit
- 403 `Result`、member 隐藏写按钮

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/users/UsersPage.tsx frontend/src/features/settings/users/UsersPage.css
git commit -m "feat(user): implement users management page"
```

---

### Task 11: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 添加 `users.*` 键**

至少包含：

- `users.add`, `users.edit`, `users.email`, `users.password`, `users.nickname`, `users.phone`, `users.status`, `users.statusNormal`, `users.statusDisabled`
- `users.membershipRole`, `users.membershipOwner`, `users.membershipAdmin`, `users.membershipMember`
- `users.department`, `users.roles`, `users.remark`, `users.search`, `users.reset`
- `users.removeMembership`, `users.removeMembershipConfirm`, `users.removeMembershipDesc`
- `users.deleteAccount`, `users.deleteAccountConfirm`, `users.deleteAccountDesc`
- `users.departmentDictMissing`
- 表单校验 message 键

- [ ] **Step 2: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "i18n: add user management strings"
```

---

### Task 12: 文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-11-user-management-design.md`
- Modify: `docs/superpowers/specs/2026-06-11-role-management-design.md`

- [ ] **Step 1: 用户管理 spec**

- 文首 **状态** → `已实现（YYYY-MM-DD）`
- 新增 **§9 实现对照** 表（ORM、SQL、service、router、UsersPage 路径）

- [ ] **Step 2: 角色管理 spec §5**

将 `sys_user_role` 从「范围外」移至已实现，链接用户管理 spec。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-user-management-design.md docs/superpowers/specs/2026-06-11-role-management-design.md
git commit -m "docs: backfill user management implementation对照"
```

---

### Task 13: 全量验证

- [ ] **Step 1: 后端测试**

Run: `cd backend && pytest tests/test_user_service.py tests/test_user_api.py tests/test_auth_status.py -v`  
Expected: 全部 PASS

- [ ] **Step 2: 前端类型检查（若项目有）**

Run: `cd frontend && npm run build`  
Expected: 无 TS 错误

- [ ] **Step 3: 手动验收清单（设计 §6.2）**

1. owner/admin 新增用户（含部门、多角色、成员资格）
2. 编辑回显；密码留空不修改
3. 邮箱/手机冲突 409 提示
4. 移出 workspace Popconfirm
5. `can_hard_delete` 控制删除账号按钮
6. `status=false` 无法登录
7. member 只读；切换 workspace 列表隔离
8. Drawer/表格滚动条为项目标准 class（非系统粗条）

---

## Spec Coverage Self-Review

| Spec 要求 | Task |
|-----------|------|
| sys_user 扩展字段 | Task 1–2 |
| 用户-角色 grant（`sys_user_grant`） | Task 1–2（初版 schema）；gateway P2/P3 迁移 |
| workspace 列表/CRUD API | Task 3–7 |
| 邮箱拒绝创建 / 手机唯一 | Task 4 |
| department 在 sys_user + workspace 校验 | Task 4 |
| 双删除 + A+B 硬删权限 | Task 4, 6 |
| status 全局 + 登录拦截 | Task 5 |
| meta/departments、meta/roles | Task 6 |
| UsersPage + Drawer + §4.4 UI | Task 9–10 |
| Popconfirm | Task 10 |
| DEFAULT_PAGE_SIZE 10 | Task 6, 10 |
| 角色 spec 交叉引用 | Task 12 |

无 TBD / 占位步骤。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-11-user-management.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立子代理，任务间做代码审查，迭代快  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，在检查点暂停供你审阅

你想用哪种方式开始实现？
