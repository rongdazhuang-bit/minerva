# 菜单管理（sys_menu）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现系统全局 `sys_menu` 的 CRUD API、RuoYi 风格管理页、动态侧边栏，并将当前 `AppLayout` 导航种子入库。

**Architecture:** 后端按 `app/sys/dict` 分层（`domain/service/infrastructure/api/utils`）；全局路由 `/sys/menus`；写权限通过 `require_any_tenant_owner_or_admin` 校验任意租户 owner/admin；删除在 service 层递归收集后代后批量删除；前端用 `GET /sys/menus/nav` 替换 `AppLayout` 硬编码 items，`router.tsx` 保持静态。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, PostgreSQL, pytest, React 18, Ant Design, TypeScript, react-i18next, @tanstack/react-query（如管理页需缓存可沿用字典页模式）。

**设计文档：** `docs/superpowers/specs/2026-06-10-menu-management-design.md`

---

## File Structure

### Backend（新建）

| 文件 | 职责 |
|------|------|
| `backend/sql/tables/sys_menu.sql` | 建表 DDL |
| `backend/sql/seeds/sys_menu_seed.sql` | 31 条侧栏种子 |
| `backend/app/sys/menu/domain/db/models.py` | `SysMenu` ORM |
| `backend/app/sys/menu/infrastructure/repository.py` | 查询/写入/批量删除 |
| `backend/app/sys/menu/service/menu_service.py` | 校验、级联删、建树编排 |
| `backend/app/sys/menu/utils/menu_tree.py` | 扁平 → 嵌套树 |
| `backend/app/sys/menu/api/schemas.py` | Pydantic |
| `backend/app/sys/menu/api/deps.py` | `require_any_tenant_owner_or_admin` |
| `backend/app/sys/menu/api/router.py` | 5 个端点 |
| `backend/tests/test_menu_tree.py` | 建树单元测试 |
| `backend/tests/test_menu_service.py` | 校验/级联删单元测试 |
| `backend/tests/test_menu_api.py` | API 集成测试 |

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/sql/schema_postgresql.sql` | 追加 `sys_menu` |
| `backend/app/core/infrastructure/db/bootstrap.py` | 注册 `SysMenu` |
| `backend/app/core/api/router.py` | `include_router(menus_router)` |
| `backend/app/core/domain/identity/services.py` | `is_any_tenant_owner_or_admin` 查询助手 |

### Frontend（新建）

| 文件 | 职责 |
|------|------|
| `frontend/src/api/menus.ts` | API 客户端 |
| `frontend/src/features/settings/menu-config/menuIconMap.ts` | 图标注册表 |
| `frontend/src/features/settings/menu-config/MenuFormDrawer.tsx` | 新增/编辑抽屉 |
| `frontend/src/app/layout/buildSiderMenuItems.tsx` | nav → Menu items |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/features/settings/menu-config/MenuConfigPage.tsx` | 完整管理页 |
| `frontend/src/app/layout/AppLayout.tsx` | 动态侧栏 + 保留 memory 过滤 |
| `frontend/src/i18n/locales/zh-CN.json` | 菜单管理文案 |
| `frontend/src/i18n/locales/en.json` | 菜单管理文案 |

---

## 种子 UUID 约定

实现 `sys_menu_seed.sql` 时使用下列固定 UUID（`ON CONFLICT (id) DO NOTHING`）：

| id | menu_key |
|----|----------|
| `00000000-0000-4000-8000-00000101` | `overview` |
| `00000000-0000-4000-8000-00000102` | `sub-agents` |
| `00000000-0000-4000-8000-00000103` | `agents-chat` |
| `00000000-0000-4000-8000-00000104` | `agents-skills` |
| `00000000-0000-4000-8000-00000105` | `agents-memory` |
| `00000000-0000-4000-8000-00000106` | `sub-doc-translate` |
| `00000000-0000-4000-8000-00000107` | `doc-translate-translate` |
| `00000000-0000-4000-8000-00000108` | `sub-dataset` |
| `00000000-0000-4000-8000-00000109` | `dataset-list` |
| `00000000-0000-4000-8000-00000110` | `sub-smart-review` |
| `00000000-0000-4000-8000-00000111` | `smart-review-text-proofreading` |
| `00000000-0000-4000-8000-00000112` | `smart-review-text-to-text` |
| `00000000-0000-4000-8000-00000113` | `smart-review-drawing-review` |
| `00000000-0000-4000-8000-00000114` | `sub-rules` |
| `00000000-0000-4000-8000-00000115` | `rules-overview` |
| `00000000-0000-4000-8000-00000116` | `rules-mgmt-list` |
| `00000000-0000-4000-8000-00000117` | `sub-rules-config` |
| `00000000-0000-4000-8000-00000118` | `rules-config-config-prompts` |
| `00000000-0000-4000-8000-00000119` | `sub-file-ocr` |
| `00000000-0000-4000-8000-00000120` | `file-ocr-overview` |
| `00000000-0000-4000-8000-00000121` | `file-ocr-tasks` |
| `00000000-0000-4000-8000-00000122` | `sub-settings` |
| `00000000-0000-4000-8000-00000123` | `settings-models` |
| `00000000-0000-4000-8000-00000124` | `settings-ocr` |
| `00000000-0000-4000-8000-00000125` | `settings-file-storage` |
| `00000000-0000-4000-8000-00000126` | `settings-celery` |
| `00000000-0000-4000-8000-00000127` | `settings-data-sources` |
| `00000000-0000-4000-8000-00000128` | `settings-menus` |
| `00000000-0000-4000-8000-00000129` | `settings-users` |
| `00000000-0000-4000-8000-00000130` | `settings-roles` |
| `00000000-0000-4000-8000-00000131` | `settings-dictionary` |

---

### Task 1: SQL 建表与种子

**Files:**
- Create: `backend/sql/tables/sys_menu.sql`
- Create: `backend/sql/seeds/sys_menu_seed.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 编写 `backend/sql/tables/sys_menu.sql`**

```sql
CREATE TABLE IF NOT EXISTS public.sys_menu (
  id            UUID         NOT NULL,
  parent_id     UUID         NULL,
  menu_name     VARCHAR(64)  NOT NULL,
  i18n_key      VARCHAR(128) NULL,
  menu_key      VARCHAR(64)  NULL,
  order_num     INT          NOT NULL DEFAULT 0,
  path          VARCHAR(256) NULL,
  menu_type     CHAR(1)      NOT NULL,
  perms         VARCHAR(128) NULL,
  icon          VARCHAR(64)  NULL,
  visible       BOOLEAN      NOT NULL DEFAULT true,
  status        BOOLEAN      NOT NULL DEFAULT true,
  is_external   BOOLEAN      NOT NULL DEFAULT false,
  remark        VARCHAR(500) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_menu_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_menu_parent_id ON public.sys_menu (parent_id);
CREATE INDEX IF NOT EXISTS ix_sys_menu_menu_type ON public.sys_menu (menu_type);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_menu_menu_key
  ON public.sys_menu (menu_key) WHERE menu_key IS NOT NULL;
COMMENT ON TABLE public.sys_menu IS '系统菜单（全局）';
COMMENT ON COLUMN public.sys_menu.parent_id IS '父菜单 id；NULL 为根';
```

- [ ] **Step 2: 编写 `backend/sql/seeds/sys_menu_seed.sql`**

按设计文档 §6 附录，为 31 行写入 `INSERT INTO sys_menu (...)` ，使用上表 UUID 与 `parent_id`。示例前两行：

```sql
INSERT INTO public.sys_menu (id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status)
VALUES
  ('00000000-0000-4000-8000-00000101', NULL, '概览', 'nav.overview', 'overview', 1, '/app/overview', 'C', 'BarChartOutlined', true, true),
  ('00000000-0000-4000-8000-00000102', NULL, '智能体', 'nav.agents', 'sub-agents', 2, NULL, 'M', 'RobotOutlined', true, true)
ON CONFLICT (id) DO NOTHING;
```

其余 29 行按 spec 附录补全（`order_num` 与侧栏顺序一致）。

- [ ] **Step 3: 将 `sys_menu` DDL 追加到 `backend/sql/schema_postgresql.sql`**

放在 `sys_dict_item` 段之后、`sys_models` 之前。

- [ ] **Step 4: 本地验证 SQL 语法**

Run: `psql -U minerva -d minerva -f backend/sql/tables/sys_menu.sql`（或 dev 库）  
Run: `psql -U minerva -d minerva -f backend/sql/seeds/sys_menu_seed.sql`  
Expected: 无 ERROR；`SELECT count(*) FROM sys_menu` ≥ 31

---

### Task 2: ORM 与 bootstrap 注册

**Files:**
- Create: `backend/app/sys/menu/__init__.py`（空）
- Create: `backend/app/sys/menu/domain/__init__.py`
- Create: `backend/app/sys/menu/domain/db/__init__.py`
- Create: `backend/app/sys/menu/domain/db/models.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`

- [ ] **Step 1: 实现 `SysMenu` 模型**

```python
"""SQLAlchemy model for global navigation menus."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysMenu(Base):
    """Global sidebar/menu row; parent_id references another sys_menu.id (app-enforced)."""

    __tablename__ = "sys_menu"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    menu_name: Mapped[str] = mapped_column(String(64), nullable=False)
    i18n_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    menu_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_num: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa.text("0"))
    path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    menu_type: Mapped[str] = mapped_column(String(1), nullable=False)
    perms: Mapped[str | None] = mapped_column(String(128), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    status: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false())
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: 在 `_import_models()` 追加**

```python
import app.sys.menu.domain.db.models  # noqa: F401
```

- [ ] **Step 3: 确认 AUTO_CREATE_TABLES 可建表**

Run: `cd backend && python -c "import asyncio; from app.core.infrastructure.db.bootstrap import create_missing_tables; asyncio.run(create_missing_tables())"`  
Expected: 无异常（需 dev `.env` 可连库）

---

### Task 3: `menu_tree` 工具与单元测试

**Files:**
- Create: `backend/app/sys/menu/utils/__init__.py`
- Create: `backend/app/sys/menu/utils/menu_tree.py`
- Create: `backend/tests/test_menu_tree.py`

- [ ] **Step 1: 写失败测试**

```python
"""Unit tests for sys_menu tree builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.sys.menu.domain.db.models import SysMenu
from app.sys.menu.utils.menu_tree import build_menu_tree


def _row(*, id: uuid.UUID, parent_id: uuid.UUID | None, order_num: int, name: str) -> SysMenu:
    return SysMenu(
        id=id,
        parent_id=parent_id,
        menu_name=name,
        menu_type="C",
        order_num=order_num,
        visible=True,
        status=True,
        is_external=False,
        create_at=datetime.now(UTC),
    )


def test_build_menu_tree_nested_and_sorted() -> None:
    root_id = uuid.uuid4()
    child_a = uuid.uuid4()
    child_b = uuid.uuid4()
    flat = [
        _row(id=child_b, parent_id=root_id, order_num=2, name="B"),
        _row(id=root_id, parent_id=None, order_num=1, name="Root"),
        _row(id=child_a, parent_id=root_id, order_num=1, name="A"),
    ]
    tree = build_menu_tree(flat)
    assert len(tree) == 1
    assert tree[0].menu_name == "Root"
    assert [c.menu_name for c in tree[0].children] == ["A", "B"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_menu_tree.py::test_build_menu_tree_nested_and_sorted -v`  
Expected: FAIL `ModuleNotFoundError` 或 `ImportError`

- [ ] **Step 3: 实现 `menu_tree.py`**

```python
"""Build nested menu trees from flat SysMenu rows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.menu.domain.db.models import SysMenu


@dataclass
class _Node:
    row: SysMenu
    children: list[_Node] = field(default_factory=list)


def _sort_nodes(nodes: list[_Node]) -> None:
    nodes.sort(key=lambda n: (n.row.order_num, n.row.menu_name))
    for n in nodes:
        _sort_nodes(n.children)


def _to_out(n: _Node) -> SysMenuNodeOut:
    return SysMenuNodeOut(
        id=n.row.id,
        parent_id=n.row.parent_id,
        menu_name=n.row.menu_name,
        i18n_key=n.row.i18n_key,
        menu_key=n.row.menu_key,
        order_num=n.row.order_num,
        path=n.row.path,
        menu_type=n.row.menu_type,
        perms=n.row.perms,
        icon=n.row.icon,
        visible=n.row.visible,
        status=n.row.status,
        is_external=n.row.is_external,
        remark=n.row.remark,
        create_at=n.row.create_at,
        update_at=n.row.update_at,
        children=[_to_out(c) for c in n.children],
    )


def build_menu_tree(flat: list[SysMenu]) -> list[SysMenuNodeOut]:
    if not flat:
        return []
    by_id: dict[uuid.UUID, _Node] = {r.id: _Node(r) for r in flat}
    roots: list[_Node] = []
    for r in flat:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            by_id[r.parent_id].children.append(node)
        else:
            roots.append(node)
    _sort_nodes(roots)
    return [_to_out(n) for n in roots]
```

- [ ] **Step 4: 先创建最小 `api/schemas.py` 中的 `SysMenuNodeOut`**（Task 6 会扩展，此处仅满足建树）

```python
class SysMenuNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    parent_id: uuid.UUID | None
    menu_name: str
    i18n_key: str | None = None
    menu_key: str | None = None
    order_num: int
    path: str | None = None
    menu_type: str
    perms: str | None = None
    icon: str | None = None
    visible: bool
    status: bool
    is_external: bool
    remark: str | None = None
    create_at: datetime | None = None
    update_at: datetime | None = None
    children: list[SysMenuNodeOut] = Field(default_factory=list)
```

- [ ] **Step 5: 运行测试通过**

Run: `cd backend && pytest tests/test_menu_tree.py -v`  
Expected: PASS

---

### Task 4: Repository 层

**Files:**
- Create: `backend/app/sys/menu/infrastructure/__init__.py`
- Create: `backend/app/sys/menu/infrastructure/repository.py`

- [ ] **Step 1: 实现 repository**

```python
"""Persistence helpers for sys_menu."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.menu.domain.db.models import SysMenu


async def list_all(session: AsyncSession) -> list[SysMenu]:
    r = await session.execute(select(SysMenu))
    return list(r.scalars().all())


async def get_by_id(session: AsyncSession, menu_id: uuid.UUID) -> SysMenu | None:
    return await session.get(SysMenu, menu_id)


async def add(session: AsyncSession, row: SysMenu) -> SysMenu:
    session.add(row)
    await session.flush()
    return row


async def delete_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> int:
    if not ids:
        return 0
    r = await session.execute(delete(SysMenu).where(SysMenu.id.in_(ids)))
    return int(r.rowcount or 0)
```

---

### Task 5: Service 层（校验 + 级联删除）与单元测试

**Files:**
- Create: `backend/app/sys/menu/service/__init__.py`
- Create: `backend/app/sys/menu/service/menu_service.py`
- Create: `backend/tests/test_menu_service.py`

- [ ] **Step 1: 写失败测试（级联删除计数）**

```python
"""Unit tests for menu_service helpers."""

from __future__ import annotations

import uuid

from app.sys.menu.service.menu_service import collect_descendant_ids


def test_collect_descendant_ids_deep() -> None:
    a, b, c, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parent_map = {a: [b], b: [c, d]}
    got = collect_descendant_ids(parent_map, a)
    assert got == {b, c, d}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_menu_service.py::test_collect_descendant_ids_deep -v`  
Expected: FAIL

- [ ] **Step 3: 实现 `menu_service.py` 核心函数**

```python
def collect_descendant_ids(
    parent_to_children: dict[uuid.UUID, list[uuid.UUID]],
    root: uuid.UUID,
) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    stack = list(parent_to_children.get(root, []))
    while stack:
        cid = stack.pop()
        if cid in out:
            continue
        out.add(cid)
        stack.extend(parent_to_children.get(cid, []))
    return out


def _build_parent_map(rows: list[SysMenu]) -> dict[uuid.UUID, list[uuid.UUID]]:
    m: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for row in rows:
        if row.parent_id is not None:
            m[row.parent_id].append(row.id)
    return m


def validate_hierarchy(
    *,
    menu_type: str,
    path: str | None,
    perms: str | None,
    parent: SysMenu | None,
) -> None:
    if menu_type == "C" and not (path and path.strip()):
        raise AppError("menu.path_required", "Menu type C requires path", 400)
    if menu_type == "F" and not (perms and perms.strip()):
        raise AppError("menu.perms_required", "Menu type F requires perms", 400)
    if parent is not None:
        if menu_type == "F" and parent.menu_type != "C":
            raise AppError("menu.invalid_hierarchy", "Button must be under menu C", 400)
        if menu_type in ("M", "C") and parent.menu_type == "F":
            raise AppError("menu.invalid_hierarchy", "Cannot place under button F", 400)


async def delete_menu_cascade(session: AsyncSession, menu_id: uuid.UUID) -> int:
    row = await repo.get_by_id(session, menu_id)
    if row is None:
        raise AppError("menu.not_found", "Menu not found", 404)
    all_rows = await repo.list_all(session)
    parent_map = _build_parent_map(all_rows)
    descendants = collect_descendant_ids(parent_map, menu_id)
    ids = list(descendants | {menu_id})
    await repo.delete_by_ids(session, ids)
    await session.commit()
    return len(ids)
```

补全 `create_menu` / `update_menu` / `list_menu_tree` / `list_nav_tree`（nav 过滤 `menu_type in ('M','C') and visible and status`）。

- [ ] **Step 4: 运行 service 测试**

Run: `cd backend && pytest tests/test_menu_service.py -v`  
Expected: PASS

---

### Task 6: API schemas、deps、router 与集成测试

**Files:**
- Create: `backend/app/sys/menu/api/__init__.py`
- Modify: `backend/app/sys/menu/api/schemas.py`（补全 In/Out）
- Create: `backend/app/sys/menu/api/deps.py`
- Create: `backend/app/sys/menu/api/router.py`
- Modify: `backend/app/core/domain/identity/services.py`
- Create: `backend/tests/test_menu_api.py`

- [ ] **Step 1: 在 `identity/services.py` 添加**

```python
async def is_any_tenant_owner_or_admin(
    session: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    r = await session.execute(
        select(TenantMembership.id).where(
            TenantMembership.user_id == user_id,
            TenantMembership.role.in_((MembershipRole.owner, MembershipRole.admin)),
        ).limit(1)
    )
    return r.scalar_one_or_none() is not None
```

- [ ] **Step 2: 实现 `deps.py`**

```python
async def require_any_tenant_owner_or_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    if not await is_any_tenant_owner_or_admin(session, user_id=user.id):
        raise AppError("auth.forbidden", "Only tenant owner/admin can manage menus", 403)
    return user
```

- [ ] **Step 3: 实现 `router.py`**

```python
router = APIRouter(prefix="/sys/menus", tags=["menus"])

@router.get("", response_model=list[SysMenuNodeOut])
async def list_menus(..., _admin: User = Depends(require_any_tenant_owner_or_admin)):
    ...

@router.get("/nav", response_model=list[SysMenuNodeOut])
async def list_nav(..., _user: User = Depends(get_current_user)):
    ...

@router.post("", response_model=SysMenuOut, status_code=201)
async def create_menu(...): ...

@router.patch("/{menu_id}", response_model=SysMenuOut)
async def patch_menu(...): ...

@router.delete("/{menu_id}", response_model=MenuDeleteOut)
async def delete_menu(...):
    # returns {"deleted_count": n}
```

- [ ] **Step 4: 注册路由**

`backend/app/core/api/router.py`:

```python
from app.sys.menu.api.router import router as menus_router
...
api.include_router(menus_router)
```

- [ ] **Step 5: 写 API 集成测试**

```python
"""Integration tests for /sys/menus routes."""

from fastapi.testclient import TestClient

def test_nav_ok_authenticated(auth_client: TestClient) -> None:
    r = auth_client.get("/sys/menus/nav")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_list_forbidden_for_member(member_menu_client: TestClient) -> None:
    r = member_menu_client.get("/sys/menus")
    assert r.status_code == 403

def test_delete_cascade_returns_count(admin_menu_client: TestClient) -> None:
    # 创建父+子后 DELETE 父，断言 deleted_count == 2
    ...
```

在 `conftest.py` 或 `test_menu_api.py` 内构建最小 FastAPI app，`dependency_overrides` 注入 `get_current_user` 与 `require_any_tenant_owner_or_admin`（参照 `test_skills_mgmt_api.py` 模式）。

- [ ] **Step 6: 运行 API 测试**

Run: `cd backend && pytest tests/test_menu_api.py tests/test_menu_tree.py tests/test_menu_service.py -v`  
Expected: 全部 PASS

---

### Task 7: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/menus.ts`

- [ ] **Step 1: 实现类型与函数**

```typescript
import { apiJson } from '@/api/client'

export type SysMenuNode = {
  id: string
  parent_id: string | null
  menu_name: string
  i18n_key: string | null
  menu_key: string | null
  order_num: number
  path: string | null
  menu_type: 'M' | 'C' | 'F'
  perms: string | null
  icon: string | null
  visible: boolean
  status: boolean
  is_external: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
  children?: SysMenuNode[]
}

export type SysMenuCreateBody = { ... }
export type SysMenuPatchBody = Partial<SysMenuCreateBody>

export function listMenus(params?: { menu_name?: string; status?: boolean }) {
  const sp = new URLSearchParams()
  if (params?.menu_name) sp.set('menu_name', params.menu_name)
  if (params?.status != null) sp.set('status', String(params.status))
  const q = sp.toString()
  return apiJson<SysMenuNode[]>(`/sys/menus${q ? `?${q}` : ''}`)
}

export function listNavMenus() {
  return apiJson<SysMenuNode[]>('/sys/menus/nav')
}

export function createMenu(body: SysMenuCreateBody) {
  return apiJson<SysMenuNode>('/sys/menus', { method: 'POST', body: JSON.stringify(body) })
}

export function patchMenu(id: string, body: SysMenuPatchBody) {
  return apiJson<SysMenuNode>(`/sys/menus/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export function deleteMenu(id: string) {
  return apiJson<{ deleted_count: number }>(`/sys/menus/${id}`, { method: 'DELETE' })
}
```

---

### Task 8: 图标映射与侧栏构建器

**Files:**
- Create: `frontend/src/features/settings/menu-config/menuIconMap.ts`
- Create: `frontend/src/app/layout/buildSiderMenuItems.tsx`

- [ ] **Step 1: `menuIconMap.ts`**

从当前 `AppLayout.tsx` imports 导出 `Record<string, React.ReactNode>`，键为图标名字符串（与种子 `icon` 列一致）。

- [ ] **Step 2: `buildSiderMenuItems.tsx`**

```typescript
import type { MenuProps } from 'antd'
import type { TFunction } from 'i18next'
import type { SysMenuNode } from '@/api/menus'
import { menuIconMap } from '@/features/settings/menu-config/menuIconMap'

export function buildSiderMenuItems(
  nodes: SysMenuNode[],
  opts: { t: TFunction; nav: (path: string) => void; hideMenuKeys?: Set<string> },
): MenuProps['items'] {
  return nodes
    .filter((n) => !n.menu_key || !opts.hideMenuKeys?.has(n.menu_key))
    .map((n) => {
      const hasChildren = (n.children?.length ?? 0) > 0
      const label = n.i18n_key ? opts.t(n.i18n_key) : n.menu_name
      const iconName = n.icon ?? undefined
      const icon = iconName && menuIconMap[iconName] ? menuIconMap[iconName] : undefined
      if (hasChildren) {
        return {
          key: n.menu_key ?? n.id,
          icon,
          label,
          children: buildSiderMenuItems(n.children!, opts),
        }
      }
      return {
        key: n.menu_key ?? n.id,
        icon,
        label,
        onClick: () => {
          if (!n.path) return
          if (n.is_external) window.open(n.path, '_blank', 'noopener')
          else opts.nav(n.path)
        },
      }
    })
}
```

---

### Task 9: 管理页 UI

**Files:**
- Create: `frontend/src/features/settings/menu-config/MenuFormDrawer.tsx`
- Modify: `frontend/src/features/settings/menu-config/MenuConfigPage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 添加 i18n 键**

`menuConfig.title`, `menuConfig.add`, `menuConfig.edit`, `menuConfig.deleteConfirm`, `menuConfig.deleteDesc`, `menuConfig.deletedCount`, `menuConfig.forbidden`, `menuConfig.menuType.M/C/F`, `menuConfig.fields.*` 等。

- [ ] **Step 2: 实现 `MenuFormDrawer.tsx`**

- Ant Design `Drawer` + `Form`
- `menu_type` Radio 切换字段显隐（见 spec §4.2）
- 上级菜单 `TreeSelect`，数据来自扁平化树
- `allowClear` on 文本/选择（code-comments 约定）

- [ ] **Step 3: 实现 `MenuConfigPage.tsx`**

参照 `DictionaryPage.tsx` 模式：

- 顶栏：搜索、`status` Select、展开/折叠、`新增`
- `Table` `expandable` 树形数据（将 API 树扁平化带 `children` 或直接用树数据）
- 列：名称、图标（`menuIconMap` 渲染）、排序、perms、path、status `Tag`、create_at、操作
- 删除：`Popconfirm` + `countDescendants(node)` 显示子节点数
- 403 时 `Result status="403"`

- [ ] **Step 4: 手动冒烟**

Run frontend dev server，以租户 admin 登录 `/app/settings/menus`，验证列表、新增、编辑、级联删除。

---

### Task 10: AppLayout 动态侧栏

**Files:**
- Modify: `frontend/src/app/layout/AppLayout.tsx`

- [ ] **Step 1: 删除硬编码 `items={[...]}` 大块**

- [ ] **Step 2: 增加 state + effect**

```typescript
const [navMenus, setNavMenus] = useState<SysMenuNode[]>([])
useEffect(() => {
  if (!isAuthenticated) return
  void listNavMenus()
    .then(setNavMenus)
    .catch(() => setNavMenus([]))
}, [isAuthenticated])
```

- [ ] **Step 3: 构建 items**

```typescript
const hideMenuKeys = memoryBackend !== 'mem0' ? new Set(['agents-memory']) : undefined
const siderItems = useMemo(
  () => buildSiderMenuItems(navMenus, { t, nav, hideMenuKeys }),
  [navMenus, t, nav, memoryBackend],
)
```

`<Menu items={siderItems} ... />`

- [ ] **Step 4: 保留 `menuKeyForPath` / `openKeys` 逻辑不变**

- [ ] **Step 5: 手动验证侧栏**

登录后侧栏与改前一致；`visible=false` 的菜单在 DB 修改刷新后隐藏。

---

### Task 11: 文档回填与全量验证

**Files:**
- Modify: `docs/superpowers/specs/2026-06-10-menu-management-design.md`

- [ ] **Step 1: 更新 spec 状态与实现对照表**

将 §9 实现对照填入实际文件路径；状态改为「已实现」。

- [ ] **Step 2: 运行后端测试全量**

Run: `cd backend && pytest tests/test_menu_api.py tests/test_menu_tree.py tests/test_menu_service.py -v`

- [ ] **Step 3: 手动验收清单（spec §7.2）**

1. 租户 admin CRUD  
2. 级联删除 Popconfirm + deleted_count 提示  
3. 侧栏与种子一致  
4. mem0 过滤 memory 菜单  
5. member 403

---

## Spec Coverage Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 全局 sys_menu 单表 | Task 1–2 |
| 无 component 字段 | Task 1 |
| 级联删除 + deleted_count | Task 5–6 |
| 租户 owner/admin 写权限 | Task 6 |
| GET /nav 动态侧栏 | Task 6, 8, 10 |
| 种子 31 节点 | Task 1 |
| RuoYi 管理页 UI | Task 9 |
| Popconfirm 删除 | Task 9 |
| agents-memory 客户端过滤 | Task 8, 10 |
| 范围外（角色授权等） | 未纳入 |

无 TBD / 占位步骤。
