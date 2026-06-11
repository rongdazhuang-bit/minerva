# 用户表单：空间角色权限与超管租户/空间选择 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在用户管理新建/编辑表单中，按操作者 workspace 角色限制「空间角色」可见性与可分配值；平台超管新建时可级联选择租户与工作空间，并将用户写入所选 workspace。

**Architecture:** 后端在 `user_service` 集中实现 capabilities 与 `membership_role` 校验矩阵；新增 `meta/capabilities` 与 `require_workspace_manager_or_super_admin` 写旁路；创建时非超管强制 `path.workspace_id == JWT.wid`。前端 `UserFormDrawer` 基于 capabilities 条件渲染，超管新建时以 `effectiveWorkspaceId` 拉 meta 并回传 `targetWorkspaceId` 给 `UsersPage`。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, pytest, React 18, Ant Design 6, TypeScript, react-i18next, @tanstack/react-query。

**设计文档：** `docs/superpowers/specs/2026-06-12-user-form-membership-tenant-design.md`

---

## File Structure

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/app/sys/user/service/user_service.py` | `resolve_assignable_membership_roles`、`get_actor_capabilities`、`assert_membership_role_assignable`；`create_user`/`update_user` 接入校验 |
| `backend/app/sys/user/api/schemas.py` | `SysUserCapabilitiesOut` |
| `backend/app/sys/user/api/router.py` | `GET meta/capabilities`；写路由换依赖；create 增加 JWT wid 校验 |
| `backend/app/sys/user/api/deps.py` | **新建** `require_workspace_manager_or_super_admin` |
| `backend/tests/test_user_service.py` | capabilities 与 membership 校验单元测试 |
| `backend/tests/test_user_api.py` | capabilities 路由与 create/patch  forbidden 集成测试 |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/api/users.ts` | `SysUserCapabilities`、`getUserCapabilities` |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | capabilities、租户/空间级联、空间角色条件渲染 |
| `frontend/src/features/settings/users/UsersPage.tsx` | `targetWorkspaceId`、跨空间成功提示 |
| `frontend/src/i18n/locales/zh-CN.json` | `users.*`、`apiErrors.user.membership_role_forbidden` |
| `frontend/src/i18n/locales/en.json` | 同上 |

### Docs（修改）

| 文件 | 变更 |
|------|------|
| `docs/superpowers/specs/2026-06-12-user-form-membership-tenant-design.md` | 状态 → 已实现；实现对照表 |
| `docs/superpowers/specs/2026-06-11-user-management-design.md` | §5 范围外删除「tenant 级用户管理」或加注「超管跨空间创建已实现于 2026-06-12 spec」 |

---

## Task 1: Service 层 — 可分配角色与 capabilities

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Test: `backend/tests/test_user_service.py`

- [ ] **Step 1: 编写失败测试 — `resolve_assignable_membership_roles`**

在 `backend/tests/test_user_service.py` 末尾追加：

```python
@pytest.mark.parametrize(
    ("actor_role", "is_super", "has_membership", "expected"),
    [
        (MembershipRole.owner, False, True, ["owner", "member"]),
        (MembershipRole.admin, False, True, ["admin", "member"]),
        (MembershipRole.member, False, True, []),
        (None, True, False, ["owner", "admin", "member"]),
        (MembershipRole.admin, True, True, ["admin", "member"]),
    ],
)
def test_resolve_assignable_membership_roles(
    actor_role: MembershipRole | None,
    is_super: bool,
    has_membership: bool,
    expected: list[str],
) -> None:
    """Assignable membership roles follow actor matrix."""

    roles = svc.resolve_assignable_membership_roles(
        actor_workspace_role=actor_role,
        actor_is_super_admin=is_super,
        actor_has_workspace_membership=has_membership,
    )
    assert roles == expected
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend
pytest tests/test_user_service.py::test_resolve_assignable_membership_roles -v
```

Expected: FAIL — `AttributeError: module ... has no attribute 'resolve_assignable_membership_roles'`

- [ ] **Step 3: 在 `user_service.py` 实现纯函数**

在 `DEPARTMENT_DICT_CODE` 下方添加：

```python
def resolve_assignable_membership_roles(
    *,
    actor_workspace_role: MembershipRole | None,
    actor_is_super_admin: bool,
    actor_has_workspace_membership: bool,
) -> list[str]:
    """Return membership_role values the actor may assign in a workspace."""

    if actor_is_super_admin and not actor_has_workspace_membership:
        return [
            MembershipRole.owner.value,
            MembershipRole.admin.value,
            MembershipRole.member.value,
        ]
    if actor_workspace_role == MembershipRole.owner:
        return [MembershipRole.owner.value, MembershipRole.member.value]
    if actor_workspace_role == MembershipRole.admin:
        return [MembershipRole.admin.value, MembershipRole.member.value]
    return []


def can_edit_membership_role(
    *,
    actor_workspace_role: MembershipRole | None,
    actor_is_super_admin: bool,
    actor_has_workspace_membership: bool,
) -> bool:
    """True when the actor may change membership_role on create/patch."""

    if actor_is_super_admin and not actor_has_workspace_membership:
        return True
    return actor_workspace_role in (MembershipRole.owner, MembershipRole.admin)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_resolve_assignable_membership_roles -v
```

Expected: PASS（5 cases）

- [ ] **Step 5: 编写失败测试 — `assert_membership_role_assignable`**

```python
@pytest.mark.asyncio
async def test_assert_membership_role_owner_cannot_assign_admin() -> None:
    """Workspace owner cannot assign admin membership."""

    with pytest.raises(AppError) as exc:
        svc.assert_membership_role_assignable(
            membership_role=MembershipRole.admin,
            assignable_roles=["owner", "member"],
            target_current_role=None,
            actor_workspace_role=MembershipRole.owner,
        )
    assert exc.value.code == "user.membership_role_forbidden"


@pytest.mark.asyncio
async def test_assert_membership_role_admin_cannot_patch_owner() -> None:
    """Workspace admin cannot change an owner's membership_role."""

    with pytest.raises(AppError) as exc:
        svc.assert_membership_role_assignable(
            membership_role=MembershipRole.member,
            assignable_roles=["admin", "member"],
            target_current_role=MembershipRole.owner,
            actor_workspace_role=MembershipRole.admin,
        )
    assert exc.value.code == "user.membership_role_forbidden"
```

- [ ] **Step 6: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_assert_membership_role_owner_cannot_assign_admin tests/test_user_service.py::test_assert_membership_role_admin_cannot_patch_owner -v
```

- [ ] **Step 7: 实现 `assert_membership_role_assignable`**

```python
def assert_membership_role_assignable(
    *,
    membership_role: MembershipRole,
    assignable_roles: list[str],
    target_current_role: MembershipRole | None,
    actor_workspace_role: MembershipRole | None,
) -> None:
    """Raise AppError when membership_role assignment is not allowed."""

    if (
        target_current_role == MembershipRole.owner
        and actor_workspace_role == MembershipRole.admin
    ):
        raise AppError(
            "user.membership_role_forbidden",
            "Cannot change workspace owner membership role",
            403,
        )
    if membership_role.value not in assignable_roles:
        raise AppError(
            "user.membership_role_forbidden",
            "Membership role is not assignable by current actor",
            400,
        )
```

- [ ] **Step 8: 运行测试确认通过**

```bash
pytest tests/test_user_service.py -k "assignable_membership or assert_membership_role" -v
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/sys/user/service/user_service.py backend/tests/test_user_service.py
git commit -m "feat(sys/user): add membership role assignment matrix helpers"
```

---

## Task 2: Service 层 — `get_actor_capabilities` 与 create/update 接入

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Test: `backend/tests/test_user_service.py`

- [ ] **Step 1: 编写失败测试 — `get_actor_capabilities`**

```python
@pytest.mark.asyncio
async def test_get_actor_capabilities_admin(monkeypatch) -> None:
    """Admin actor receives admin/member assignable roles."""

    session = AsyncMock()
    actor_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    async def fake_is_super(_session: object, *, user_id: uuid.UUID) -> bool:
        return False

    async def fake_find_role(
        _session: object, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipRole | None:
        return MembershipRole.admin

    monkeypatch.setattr(svc, "is_super_admin_user", fake_is_super)
    monkeypatch.setattr(
        "app.sys.user.service.user_service.find_workspace_role_for_user",
        fake_find_role,
    )

    caps = await svc.get_actor_capabilities(
        session, workspace_id=ws_id, actor_user_id=actor_id
    )
    assert caps["can_edit_membership_role"] is True
    assert caps["assignable_membership_roles"] == ["admin", "member"]
    assert caps["can_pick_tenant_workspace"] is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_get_actor_capabilities_admin -v
```

- [ ] **Step 3: 实现 `get_actor_capabilities`**

在 `user_service.py` 顶部增加 import：

```python
from app.core.domain.identity.services import (
    find_workspace_role_for_user,
    is_super_admin_user,
)
```

实现：

```python
async def get_actor_capabilities(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> dict[str, object]:
    """Build form capability flags for the actor in a target workspace."""

    actor_is_super = await is_super_admin_user(session, user_id=actor_user_id)
    actor_role = await find_workspace_role_for_user(
        session, user_id=actor_user_id, workspace_id=workspace_id
    )
    has_membership = actor_role is not None
    assignable = resolve_assignable_membership_roles(
        actor_workspace_role=actor_role,
        actor_is_super_admin=actor_is_super,
        actor_has_workspace_membership=has_membership,
    )
    return {
        "is_super_admin": actor_is_super,
        "actor_workspace_role": actor_role.value if actor_role else None,
        "can_edit_membership_role": can_edit_membership_role(
            actor_workspace_role=actor_role,
            actor_is_super_admin=actor_is_super,
            actor_has_workspace_membership=has_membership,
        ),
        "assignable_membership_roles": assignable,
        "can_pick_tenant_workspace": actor_is_super,
    }
```

- [ ] **Step 4: 在 `create_user` 开头接入校验**

在 `create_user` 参数列表增加 `actor_user_id: uuid.UUID`，在邮箱校验之前：

```python
    caps = await get_actor_capabilities(
        session, workspace_id=workspace_id, actor_user_id=actor_user_id
    )
    if not caps["can_edit_membership_role"] and membership_role != MembershipRole.member:
        raise AppError(
            "user.membership_role_forbidden",
            "Membership role is not assignable by current actor",
            400,
        )
    assignable = list(caps["assignable_membership_roles"])
    if caps["can_edit_membership_role"]:
        assert_membership_role_assignable(
            membership_role=membership_role,
            assignable_roles=assignable,
            target_current_role=None,
            actor_workspace_role=(
                MembershipRole(caps["actor_workspace_role"])
                if caps["actor_workspace_role"]
                else None
            ),
        )
```

- [ ] **Step 5: 在 `update_user` 中 `membership_role is not None` 分支接入**

在 `update_user` 参数增加 `actor_user_id: uuid.UUID`；在 `if membership_role is not None:` 内：

```python
        caps = await get_actor_capabilities(
            session, workspace_id=workspace_id, actor_user_id=actor_user_id
        )
        if not caps["can_edit_membership_role"]:
            raise AppError(
                "user.membership_role_forbidden",
                "Membership role is not assignable by current actor",
                403,
            )
        assert_membership_role_assignable(
            membership_role=membership_role,
            assignable_roles=list(caps["assignable_membership_roles"]),
            target_current_role=membership.role,
            actor_workspace_role=(
                MembershipRole(caps["actor_workspace_role"])
                if caps["actor_workspace_role"]
                else None
            ),
        )
```

- [ ] **Step 6: 更新 `router.py` 调用签名**

`create_user(..., actor_user_id=actor.id)`  
`update_user(..., actor_user_id=actor.id)`（`actor` 来自 `get_current_user`）

- [ ] **Step 7: 运行相关 service 测试**

```bash
pytest tests/test_user_service.py -v
```

Expected: 全部 PASS（修复因签名变更导致的 mock 测试）

- [ ] **Step 8: Commit**

```bash
git add backend/app/sys/user/service/user_service.py backend/app/sys/user/api/router.py backend/tests/test_user_service.py
git commit -m "feat(sys/user): enforce membership role matrix on create and update"
```

---

## Task 3: API — capabilities 路由与写权限旁路

**Files:**
- Create: `backend/app/sys/user/api/deps.py`
- Modify: `backend/app/sys/user/api/schemas.py`
- Modify: `backend/app/sys/user/api/router.py`
- Test: `backend/tests/test_user_api.py`

- [ ] **Step 1: 新建 `backend/app/sys/user/api/deps.py`**

```python
"""Route-level dependencies for workspace user management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import (
    get_current_user,
    require_workspace_owner_or_admin,
)
from app.core.domain.identity.models import User, Workspace
from app.core.domain.identity.services import is_super_admin_user
from app.dependencies import get_db
from app.exceptions import AppError


async def require_workspace_manager_or_super_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow workspace owner/admin or platform super admin to mutate users."""

    if await is_super_admin_user(session, user_id=user.id):
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("user.workspace_invalid", "Workspace not found", 404)
        return workspace_id
    return await require_workspace_owner_or_admin(
        workspace_id, user=user, session=session
    )
```

- [ ] **Step 2: 在 `schemas.py` 添加**

```python
class SysUserCapabilitiesOut(BaseModel):
    """Actor permissions for the user form in a target workspace."""

    is_super_admin: bool
    actor_workspace_role: str | None
    can_edit_membership_role: bool
    assignable_membership_roles: list[str]
    can_pick_tenant_workspace: bool
```

- [ ] **Step 3: 在 `router.py` 添加 capabilities 路由**

```python
from app.core.api.deps import get_current_workspace_id
from app.sys.user.api.deps import require_workspace_manager_or_super_admin
from app.sys.user.api.schemas import SysUserCapabilitiesOut

@router.get("/meta/capabilities", response_model=SysUserCapabilitiesOut)
async def get_user_capabilities(
    workspace_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    _ws: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysUserCapabilitiesOut:
    """Return form capability flags for the current actor."""

    data = await svc.get_actor_capabilities(
        session, workspace_id=workspace_id, actor_user_id=actor.id
    )
    return SysUserCapabilitiesOut.model_validate(data)
```

- [ ] **Step 4: 写路由换依赖**

将 `create_user`、`patch_user`、`remove_user_membership`、`delete_user_account` 的  
`Depends(require_workspace_owner_or_admin)` 改为  
`Depends(require_workspace_manager_or_super_admin)`。

- [ ] **Step 5: `create_user` 增加非超管 JWT wid 校验**

在 `create_user` 路由内、`svc.create_user` 之前：

```python
    actor_is_super = await is_super_admin_user(session, user_id=actor.id)
    if not actor_is_super:
        token_wid = await get_current_workspace_id(
            cred=Depends(bearer)  # 改为在路由参数注入 HTTPAuthorizationCredentials
        )
```

**实现方式（推荐）**：在 `deps.py` 再增：

```python
async def require_create_workspace_scope(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    token_workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> uuid.UUID:
    """Non-super-admin creates must target the JWT active workspace."""

    if await is_super_admin_user(session, user_id=user.id):
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("user.workspace_invalid", "Workspace not found", 404)
        return workspace_id
    if token_workspace_id != workspace_id:
        raise AppError(
            "auth.forbidden",
            "Cannot create users for a workspace other than the active one",
            403,
        )
    return await require_workspace_manager_or_super_admin(
        workspace_id, user=user, session=session
    )
```

`POST` 路由单独使用 `Depends(require_create_workspace_scope)`。

- [ ] **Step 6: 编写 API 测试 — capabilities**

在 `test_user_api.py`：

```python
def test_capabilities_ok_for_member(member_users_client: TestClient, monkeypatch) -> None:
    """Members can read capabilities meta."""

    async def _fake_caps(*_a, **_k):
        return {
            "is_super_admin": False,
            "actor_workspace_role": "member",
            "can_edit_membership_role": False,
            "assignable_membership_roles": [],
            "can_pick_tenant_workspace": False,
        }

    monkeypatch.setattr(
        "app.sys.user.api.router.svc.get_actor_capabilities",
        _fake_caps,
    )
    response = member_users_client.get(
        f"/workspaces/{WS_ID}/users/meta/capabilities"
    )
    assert response.status_code == 200
    assert response.json()["can_edit_membership_role"] is False
```

- [ ] **Step 7: 运行 API 测试**

```bash
pytest tests/test_user_api.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/sys/user/api/deps.py backend/app/sys/user/api/schemas.py backend/app/sys/user/api/router.py backend/tests/test_user_api.py
git commit -m "feat(sys/user): add capabilities meta and super-admin write bypass"
```

---

## Task 4: 前端 API 与 i18n

**Files:**
- Modify: `frontend/src/api/users.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 在 `users.ts` 添加类型与函数**

```typescript
/** Actor form capabilities for a target workspace. */
export type SysUserCapabilities = {
  is_super_admin: boolean
  actor_workspace_role: string | null
  can_edit_membership_role: boolean
  assignable_membership_roles: string[]
  can_pick_tenant_workspace: boolean
}

/** Load form capability flags for the current actor. */
export function getUserCapabilities(workspaceId: string) {
  return apiJson<SysUserCapabilities>(
    `/workspaces/${workspaceId}/users/meta/capabilities`,
  )
}
```

- [ ] **Step 2: 添加 i18n（zh-CN）**

```json
"users.tenant": "租户",
"users.workspace": "工作空间",
"users.tenantPlaceholder": "请选择租户",
"users.workspacePlaceholder": "请选择工作空间",
"users.createSuccessOtherWorkspace": "用户已添加到所选工作空间，当前列表不会显示该用户",
"users.membershipRoleReadonlyAdmin": "该用户为空间管理员，仅空间管理员可调整此角色",
"apiErrors.user.membership_role_forbidden": "当前无权分配该空间角色"
```

- [ ] **Step 3: 添加 i18n（en）**

```json
"users.tenant": "Tenant",
"users.workspace": "Workspace",
"users.tenantPlaceholder": "Select tenant",
"users.workspacePlaceholder": "Select workspace",
"users.createSuccessOtherWorkspace": "User was added to the selected workspace and will not appear in the current list",
"users.membershipRoleReadonlyAdmin": "This user is a workspace admin; only workspace admins can change this role",
"apiErrors.user.membership_role_forbidden": "You are not allowed to assign this workspace role"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/users.ts frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "feat(frontend): add user capabilities API client and i18n"
```

---

## Task 5: `UserFormDrawer` — capabilities、级联与空间角色

**Files:**
- Modify: `frontend/src/features/settings/users/UserFormDrawer.tsx`

- [ ] **Step 1: 扩展 Props**

```typescript
import { listTenants, listWorkspaces, type SysTenantListItem, type SysWorkspaceListItem } from '@/api/tenants'
import { getUserCapabilities, type SysUserCapabilities } from '@/api/users'

type Props = {
  // ...existing
  pageWorkspaceId: string | null
  onSubmit: (
    values: SysUserCreateBody | Record<string, unknown>,
    context: { targetWorkspaceId: string },
  ) => Promise<void>
}
```

- [ ] **Step 2: 状态与 `effectiveWorkspaceId`**

```typescript
const [capabilities, setCapabilities] = useState<SysUserCapabilities | null>(null)
const [tenants, setTenants] = useState<SysTenantListItem[]>([])
const [workspaces, setWorkspaces] = useState<SysWorkspaceListItem[]>([])
const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)
const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null)

const effectiveWorkspaceId = useMemo(() => {
  if (mode === 'create' && capabilities?.can_pick_tenant_workspace) {
    return selectedWorkspaceId
  }
  return pageWorkspaceId
}, [mode, capabilities, selectedWorkspaceId, pageWorkspaceId])
```

- [ ] **Step 3: 打开 Drawer 时加载 capabilities / meta**

`useEffect` 依赖 `[open, effectiveWorkspaceId]`：

- 若 `!effectiveWorkspaceId` 则跳过
- `getUserCapabilities(effectiveWorkspaceId)`
- `listUserDepartmentTree(effectiveWorkspaceId)`
- `listUserAssignableRoles(effectiveWorkspaceId)`

超管新建初次打开：先拉 capabilities（`pageWorkspaceId`），若 `can_pick_tenant_workspace` 再 `listTenants` 并默认 `selectedWorkspaceId = pageWorkspaceId`（租户通过 workspace 反查：可先 `listWorkspaces` 当前租户或 tenants 遍历 — **实现**：打开时 `listTenants`，对每个 tenant 不遍历；更简单做法：超管默认 `selectedWorkspaceId = pageWorkspaceId`，`listTenants` 后若 workspace 列表需 tenant，在 `listWorkspaces` 时用 JWT 当前 tenant：从 `AuthContext` 暂无 tenantId，**用 `listTenants` + 对每个 tenant 调 `listWorkspaces` 找到含 `pageWorkspaceId` 的 tenant** 仅初始化一次，或后端 capabilities 未来扩展 `default_tenant_id`；**本期最小实现**：超管打开新建时并行 `listTenants`，默认选中第一个 status=true 的 tenant 并 `listWorkspaces`，若 `pageWorkspaceId` 在列表中则选中它及其租户，否则选第一个 workspace。

- [ ] **Step 4: 租户 / 工作空间 Form.Item（仅 `mode==='create' && capabilities?.can_pick_tenant_workspace`）**

```tsx
<Form.Item name="tenant_id" label={t('users.tenant')} rules={[{ required: true }]}>
  <Select
    allowClear={false}
    options={tenants.map((row) => ({ value: row.id, label: row.name }))}
    onChange={(tid) => {
      setSelectedTenantId(tid)
      setSelectedWorkspaceId(null)
      form.setFieldValue('workspace_id', undefined)
      void listWorkspaces(tid).then((page) => setWorkspaces(page.items))
    }}
  />
</Form.Item>
<Form.Item name="workspace_id" label={t('users.workspace')} rules={[{ required: true }]}>
  <Select
    allowClear={false}
    options={workspaces.map((row) => ({ value: row.id, label: row.name }))}
    onChange={(wid) => setSelectedWorkspaceId(wid)}
  />
</Form.Item>
```

- [ ] **Step 5: 空间角色条件渲染**

```tsx
const membershipReadonly =
  mode === 'edit' &&
  capabilities?.can_edit_membership_role &&
  initial?.membership_role &&
  !capabilities.assignable_membership_roles.includes(initial.membership_role)

{capabilities?.can_edit_membership_role ? (
  membershipReadonly ? (
    <>
      <Alert type="info" message={t('users.membershipRoleReadonlyAdmin')} />
      <Form.Item label={t('users.membershipRole')}>
        <Input disabled value={t(`users.membershipAdmin`)} />
      </Form.Item>
    </>
  ) : (
    <Form.Item name="membership_role" label={t('users.membershipRole')} rules={[{ required: true }]}>
      <Select
        allowClear={false}
        options={capabilities.assignable_membership_roles.map((value) => ({
          value,
          label: t(
            value === 'owner'
              ? 'users.membershipOwner'
              : value === 'admin'
                ? 'users.membershipAdmin'
                : 'users.membershipMember',
          ),
        }))}
      />
    </Form.Item>
  )
) : null}
```

- [ ] **Step 6: `handleFinish` 回传 `targetWorkspaceId`**

```typescript
const targetWorkspaceId = effectiveWorkspaceId ?? pageWorkspaceId
if (!targetWorkspaceId) return
// edit patch: omit membership_role when membershipReadonly
await onSubmit(payload, { targetWorkspaceId })
```

- [ ] **Step 7: 手动验证**

启动前后端，超管新建：租户/空间级联可见；admin 操作者仅 admin/member；owner 仅 owner/member。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/settings/users/UserFormDrawer.tsx
git commit -m "feat(frontend): user form capabilities, tenant cascade, membership role UX"
```

---

## Task 6: `UsersPage` 接入 targetWorkspaceId

**Files:**
- Modify: `frontend/src/features/settings/users/UsersPage.tsx`

- [ ] **Step 1: 更新 `handleSubmit`**

```typescript
const handleSubmit = useCallback(
  async (
    values: SysUserCreateBody | Record<string, unknown>,
    context: { targetWorkspaceId: string },
  ) => {
    const { targetWorkspaceId } = context
    if (!workspaceId) return
    setSubmitting(true)
    try {
      if (drawerMode === 'create') {
        await createUser(targetWorkspaceId, values as SysUserCreateBody)
        if (targetWorkspaceId !== workspaceId) {
          messageApi.success(t('users.createSuccessOtherWorkspace'))
        } else {
          messageApi.success(t('users.createSuccess'))
        }
      } else if (editingId) {
        await patchUser(workspaceId, editingId, values as SysUserPatchBody)
        messageApi.success(t('users.updateSuccess'))
      }
      // ...
    } finally {
      setSubmitting(false)
    }
  },
  [workspaceId, drawerMode, editingId, messageApi, t, reloadList],
)
```

- [ ] **Step 2: 传 `pageWorkspaceId={workspaceId}` 给 Drawer**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/users/UsersPage.tsx
git commit -m "feat(frontend): create user in selected workspace for super admin"
```

---

## Task 7: 全量测试与文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-12-user-form-membership-tenant-design.md`
- Modify: `docs/superpowers/specs/2026-06-11-user-management-design.md`

- [ ] **Step 1: 运行后端全量用户测试**

```bash
cd backend
pytest tests/test_user_service.py tests/test_user_api.py -v
```

Expected: 全部 PASS

- [ ] **Step 2: 前端类型检查**

```bash
cd frontend
npm run build
```

Expected: 构建成功

- [ ] **Step 3: 回填设计文档**

`2026-06-12-user-form-membership-tenant-design.md`：

- 状态 → **已实现**
- 增加 §10 实现对照表（capabilities 路由、deps、UserFormDrawer 等路径）

`2026-06-11-user-management-design.md` §5 范围外表述更新。

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/
git commit -m "docs: mark user form membership/tenant spec implemented"
```

---

## Spec Coverage Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| capabilities meta | Task 2, 3 |
| membership 矩阵校验 | Task 1, 2 |
| 超管写旁路 | Task 3 |
| 非超管 create wid 限制 | Task 3 |
| admin 不可改 owner | Task 1, 2 |
| owner 编辑 admin 只读（前端） | Task 5 |
| 超管租户→空间级联 | Task 5, 6 |
| 跨空间成功提示 | Task 4, 6 |
| i18n / apiErrors | Task 4 |
| 测试 | Task 1–3, 7 |

无 TBD / 占位步骤。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-12-user-form-membership-tenant.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立子代理，任务间做代码审查，迭代快

**2. Inline Execution** — 在本会话按 Task 顺序直接实现，批次间设检查点

你想用哪种方式？
