# 数据字典全局化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `sys_dict` 从 workspace 作用域改为平台全局，API 统一为 `/sys/dicts`，并更新所有后端/前端字典调用点。

**Architecture:** 删除 `sys_dict.workspace_id` 与复合唯一约束，Repository/Service 去掉 workspace 过滤；读接口用 `require_any_workspace_member`（超管兜底），写接口用 `require_super_admin`；前端 `api/dicts.ts` 与 Query Key 去 `workspaceId`；间接调用方（翻译、模型供应商、用户部门）改调全局 Service。

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL SQL patch, pytest, React, TanStack Query, Ant Design

**Spec:** `docs/superpowers/specs/2026-06-12-dict-global-design.md`

---

## File Map

| 文件 | 职责 |
|------|------|
| `backend/sql/patches/2026-06-12-sys-dict-global.sql` | 删 `workspace_id`，加 `dict_code` 全局唯一 |
| `backend/sql/schema_postgresql.sql` | 同步 `sys_dict` 定义 |
| `backend/app/sys/dict/domain/db/models.py` | ORM 去 workspace |
| `backend/app/core/domain/identity/services.py` | `is_any_workspace_member` |
| `backend/app/sys/dict/infrastructure/repository.py` | 全局查询 |
| `backend/app/sys/dict/service/dictionary_service.py` | 全局用例 |
| `backend/app/sys/dict/api/deps.py` | 读/写鉴权 |
| `backend/app/sys/dict/api/router.py` | `/sys/dicts` 路由 |
| `backend/app/sys/dict/api/schemas.py` | 去 `workspace_id` |
| `backend/app/translate/service/translate_dict_seed.py` | 全局 seed |
| `backend/app/translate/service/job_service.py` | 调全局 seed |
| `backend/app/translate/api/router.py` | 调全局 seed |
| `backend/app/translate/service/translate_llm.py` | 去 workspace dict 参数 |
| `backend/app/sys/model_provider/service/model_provider_service.py` | 去 workspace dict 参数 |
| `backend/tests/test_dict_api.py` | API 鉴权集成测试 |
| `backend/tests/test_dict_workspace_member.py` | identity helper 单元测试 |
| `frontend/src/api/dicts.ts` | 全局 API 客户端 |
| `frontend/src/constants/dictQueryKeys.ts` | 去 workspaceId |
| `frontend/src/hooks/useDictItemTree.ts` | 去 workspaceId |
| `frontend/src/features/settings/dictionary/DictionaryPage.tsx` | 管理页 + 403 |
| `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx` | 去 workspaceId 调 dict |

---

### Task 1: 数据库 patch 与 ORM

**Files:**
- Create: `backend/sql/patches/2026-06-12-sys-dict-global.sql`
- Modify: `backend/sql/schema_postgresql.sql`（`sys_dict` 段）
- Modify: `backend/app/sys/dict/domain/db/models.py`

- [ ] **Step 1: 创建 SQL patch**

`backend/sql/patches/2026-06-12-sys-dict-global.sql`:

```sql
-- sys_dict: workspace scope -> platform global
ALTER TABLE public.sys_dict DROP CONSTRAINT IF EXISTS uq_sys_dict_workspace_dict_code;
ALTER TABLE public.sys_dict DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE public.sys_dict
  ADD CONSTRAINT uq_sys_dict_dict_code UNIQUE (dict_code);
```

- [ ] **Step 2: 更新 schema_postgresql.sql**

将 `sys_dict` 表定义改为（删除 `workspace_id` 行，约束改为 `uq_sys_dict_dict_code UNIQUE (dict_code)`）。

- [ ] **Step 3: 更新 ORM**

`backend/app/sys/dict/domain/db/models.py`:

```python
class SysDict(Base):
    """Platform-global dictionary category identified by ``dict_code``."""

    __tablename__ = "sys_dict"
    __table_args__ = (
        UniqueConstraint("dict_code", name="uq_sys_dict_dict_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dict_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # ... 其余字段不变，删除 workspace_id
```

- [ ] **Step 4: 本地执行 patch（开发库）**

Run: `psql $DATABASE_URL -f backend/sql/patches/2026-06-12-sys-dict-global.sql`  
Expected: `ALTER TABLE` ×3 成功

---

### Task 2: `is_any_workspace_member` 身份 helper

**Files:**
- Modify: `backend/app/core/domain/identity/services.py`
- Create: `backend/tests/test_dict_workspace_member.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_dict_workspace_member.py`:

```python
"""Tests for is_any_workspace_member used by global dict read gate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_any_workspace_member


@pytest.mark.asyncio
async def test_is_any_workspace_member_true_for_super_admin() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="sa@example.com",
            password_hash="x",
            nickname="SA",
            is_super_admin=True,
        )
    )
    assert await is_any_workspace_member(session, user_id=uid) is True
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_is_any_workspace_member_true_for_member() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="m@example.com",
            password_hash="x",
            nickname="M",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    session.execute = AsyncMock(return_value=result)
    assert await is_any_workspace_member(session, user_id=uid) is True


@pytest.mark.asyncio
async def test_is_any_workspace_member_false_without_membership() -> None:
    uid = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(
        return_value=User(
            id=uid,
            email="x@example.com",
            password_hash="x",
            nickname="X",
            is_super_admin=False,
        )
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    assert await is_any_workspace_member(session, user_id=uid) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_dict_workspace_member.py -v`  
Expected: FAIL `ImportError: cannot import name 'is_any_workspace_member'`

- [ ] **Step 3: 实现 helper**

在 `backend/app/core/domain/identity/services.py` 追加（需 import `WorkspaceMembership`）:

```python
async def is_any_workspace_member(
    session: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    """True when super-admin, or member of at least one workspace."""

    if await is_super_admin_user(session, user_id=user_id):
        return True
    r = await session.execute(
        select(WorkspaceMembership.id)
        .where(WorkspaceMembership.user_id == user_id)
        .limit(1)
    )
    return r.scalar_one_or_none() is not None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_dict_workspace_member.py -v`  
Expected: 3 passed

---

### Task 3: Repository 全局化

**Files:**
- Modify: `backend/app/sys/dict/infrastructure/repository.py`

- [ ] **Step 1: 重命名并去掉 workspace 过滤**

| 旧函数 | 新函数 |
|--------|--------|
| `list_dicts_for_workspace` | `list_dicts` |
| `count_dicts_for_workspace` | `count_dicts` |
| `list_dicts_for_workspace_page` | `list_dicts_page` |
| `get_dict_for_workspace` | `get_dict_by_id` |
| `get_dict_by_code_for_workspace` | `get_dict_by_code` |

所有 `SysDict.workspace_id == workspace_id` 条件删除；函数签名去掉 `workspace_id` 参数。

示例 `get_dict_by_code`:

```python
async def get_dict_by_code(
    session: AsyncSession,
    *,
    dict_code: str,
) -> SysDict | None:
    result = await session.execute(
        select(SysDict).where(SysDict.dict_code == dict_code.strip())
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 2: 全库搜索旧函数名**

Run: `rg "list_dicts_for_workspace|get_dict_by_code_for_workspace|get_dict_for_workspace" backend`  
Expected: 仅 dict 模块外间接引用（Task 7 处理）

---

### Task 4: Service 全局化

**Files:**
- Modify: `backend/app/sys/dict/service/dictionary_service.py`

- [ ] **Step 1: 去掉所有 `workspace_id` 参数**

- `list_dicts(session)` → 调 `repo.list_dicts`
- `list_dicts_page(session, page, page_size, ...)` → 调 `repo.count_dicts` / `repo.list_dicts_page`
- `get_dict(session, dict_id)` → 调 `repo.get_dict_by_id`
- `create_dict(session, dict_code, ...)` → `SysDict(...)` **不含** `workspace_id`
- `list_items_by_dict_code(session, dict_code)` → 调 `repo.get_dict_by_code`
- 其余 `list_items` / `create_item` / `update_item` / `delete_item` 同理去掉 `workspace_id`

- [ ] **Step 2: 更新冲突文案**

`_commit_or_conflict` 中 message 改为 `"Duplicate code in this dictionary"`。

---

### Task 5: Dict API deps + schemas + router

**Files:**
- Create: `backend/app/sys/dict/api/deps.py`
- Modify: `backend/app/sys/dict/api/schemas.py`
- Modify: `backend/app/sys/dict/api/router.py`

- [ ] **Step 1: 创建 deps.py**

```python
"""Authorization dependencies for global dictionary management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_any_workspace_member
from app.dependencies import get_db
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin

__all__ = ["require_any_workspace_member", "require_super_admin"]


async def require_any_workspace_member(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow super-admin or any workspace member to read dictionaries."""

    if not await is_any_workspace_member(session, user_id=user.id):
        raise AppError(
            "auth.forbidden",
            "Only super-admin or workspace members can read dictionaries",
            403,
        )
    return user
```

- [ ] **Step 2: schemas 去 workspace_id**

`SysDictListItemOut` 删除 `workspace_id: uuid.UUID` 字段。

- [ ] **Step 3: router 改为 `/sys/dicts`**

```python
router = APIRouter(prefix="/sys/dicts", tags=["dicts"])
```

- 所有 handler 去掉 `workspace_id: uuid.UUID` 路径参数
- GET 端点: `_user: User = Depends(require_any_workspace_member)`
- POST/PATCH/DELETE: `_admin: User = Depends(require_super_admin)`
- `_dict_to_list_out` 不再传 `workspace_id`
- service 调用去掉 `workspace_id=...`

---

### Task 6: Dict API 集成测试

**Files:**
- Create: `backend/tests/test_dict_api.py`

- [ ] **Step 1: 写鉴权测试**

```python
"""Integration tests for global /sys/dicts routes."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.errors import register_exception_handlers
from app.exceptions import AppError
from app.sys.dict.api.deps import require_any_workspace_member
from app.sys.dict.api.router import router as dicts_router
from app.sys.tenant.api.deps import require_super_admin

FAKE_USER = User(
    id=__import__("uuid").uuid4(),
    email="u@example.com",
    password_hash="x",
    nickname="U",
    is_super_admin=False,
)


async def _allow_reader() -> User:
    return FAKE_USER


async def _deny_reader() -> User:
    raise AppError("auth.forbidden", "denied", 403)


async def _allow_super_admin() -> User:
    u = User(
        id=FAKE_USER.id,
        email="sa@example.com",
        password_hash="x",
        nickname="SA",
        is_super_admin=True,
    )
    return u


async def _deny_super_admin() -> User:
    raise AppError("auth.forbidden", "denied", 403)


def _make_dict_app(*, reader: bool, writer: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(dicts_router)
    app.dependency_overrides[require_any_workspace_member] = (
        _allow_reader if reader else _deny_reader
    )
    app.dependency_overrides[require_super_admin] = (
        _allow_super_admin if writer else _deny_super_admin
    )
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    return app


@pytest.fixture
def reader_client() -> Iterator[TestClient]:
    with patch(
        "app.sys.dict.api.router.svc.list_dicts_page",
        new=AsyncMock(return_value=([], 0)),
    ):
        yield TestClient(_make_dict_app(reader=True, writer=False))


def test_list_dicts_forbidden_without_reader() -> None:
    client = TestClient(_make_dict_app(reader=False, writer=False))
    r = client.get("/sys/dicts")
    assert r.status_code == 403


def test_list_dicts_ok_for_reader(reader_client: TestClient) -> None:
    r = reader_client.get("/sys/dicts")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


def test_create_dict_forbidden_for_non_super_admin() -> None:
    with patch(
        "app.sys.dict.api.router.svc.create_dict",
        new=AsyncMock(),
    ):
        client = TestClient(_make_dict_app(reader=True, writer=False))
        r = client.post(
            "/sys/dicts",
            json={"dict_code": "TEST", "dict_name": "Test"},
        )
        assert r.status_code == 403
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_dict_api.py -v`  
Expected: PASS（router 已 Task 5 完成）

---

### Task 7: 后端间接调用方

**Files:**
- Modify: `backend/app/translate/service/translate_dict_seed.py`
- Modify: `backend/app/translate/service/job_service.py`
- Modify: `backend/app/translate/api/router.py`
- Modify: `backend/app/translate/service/translate_llm.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`
- Modify: `backend/app/sys/user/service/user_service.py`

- [ ] **Step 1: translate_dict_seed 全局化**

```python
async def _ensure_dict_with_items(
    session: AsyncSession,
    *,
    dict_code: str,
    dict_name: str,
    items: dict[str, tuple[str, int]],
) -> None:
    row = await dict_repo.get_dict_by_code(session, dict_code=dict_code)
    # ... 创建 SysDict 时不含 workspace_id

async def ensure_translate_status_dicts(session: AsyncSession) -> None:
    await _ensure_dict_with_items(session, dict_code=TRANSLATE_STATUS_DICT_CODE, ...)
    await _ensure_dict_with_items(session, dict_code=TRANSLATE_SEGMENT_STATUS_DICT_CODE, ...)
```

- [ ] **Step 2: 更新调用方**

`job_service.py` / `translate/api/router.py`:

```python
await ensure_translate_status_dicts(session)
```

`translate_llm.py`:

```python
async def _assert_translate_dict(session: AsyncSession) -> None:
    allowed = await dict_service.list_items_by_dict_code(
        session, dict_code=MODEL_TAG_DICT_CODE
    )
```

- [ ] **Step 3: model_provider_service**

```python
async def _load_dict_code_set(
    session: AsyncSession, *, dict_code: str
) -> set[str]:
    items = await dict_service.list_items_by_dict_code(
        session, dict_code=dict_code
    )
```

更新 `normalize_tags` / `validate_provider_name` 等内部调用，去掉 `workspace_id` 传参。

- [ ] **Step 4: user_service 部门字典**

三处 `get_dict_by_code_for_workspace(..., workspace_id, DEPARTMENT_DICT_CODE)` 改为:

```python
d = await dict_repo.get_dict_by_code(session, dict_code=DEPARTMENT_DICT_CODE)
```

`list_department_tree(session, workspace_id=...)` → `list_department_tree(session)`。

- [ ] **Step 5: 更新 test_model_provider_tags.py**

`_load_dict_code_set` mock 签名去掉 `workspace_id`；调用 `normalize_tags(session, tags=...)` 去掉 `workspace_id`。

- [ ] **Step 6: 全库验证无残留**

Run: `rg "get_dict_by_code_for_workspace|list_dicts_for_workspace|workspace_id=workspace_id.*dict" backend/app`  
Expected: 无匹配（tests 除外）

Run: `cd backend && pytest tests/test_model_provider_tags.py -v`  
Expected: PASS

---

### Task 8: 前端 API 与 Query

**Files:**
- Modify: `frontend/src/api/dicts.ts`
- Modify: `frontend/src/constants/dictQueryKeys.ts`
- Modify: `frontend/src/hooks/useDictItemTree.ts`

- [ ] **Step 1: dictQueryKeys**

```typescript
export const dictQueryKeys = {
  all: () => ['dict'] as const,
  byCode: (dictCode: string, page: number, pageSize: number) =>
    ['dict', 'byCode', dictCode, { page, pageSize }] as const,
}
```

- [ ] **Step 2: api/dicts.ts**

- `SysDictListItem` 删除 `workspace_id`
- `listDicts(params)` → `GET /sys/dicts?...`（无 workspaceId）
- `fetchDictByCode(dictCode)`、`listAllDicts()`、`createDict(body)` 等全部去掉首参 `workspaceId`
- URL 模板：`/sys/dicts`、`/sys/dicts/${dictId}/items/...`

- [ ] **Step 3: useDictItemTree**

```typescript
export function useDictItemTree(dictCode: string) {
  return useQuery({
    queryKey: dictQueryKeys.byCode(dictCode, DICT_PAGE, DICT_PAGE_SIZE),
    queryFn: () => fetchDictByCode(dictCode),
    enabled: Boolean(dictCode),
    staleTime: DICT_QUERY_STALE_MS,
    gcTime: DICT_QUERY_GC_MS,
  })
}
```

- [ ] **Step 4: TypeScript 编译**

Run: `cd frontend && npm run build`  
Expected: 报出需修复的调用方（Task 9）

---

### Task 9: 前端页面

**Files:**
- Modify: `frontend/src/features/settings/dictionary/DictionaryPage.tsx`
- Modify: `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`

- [ ] **Step 1: DictionaryPage**

- 删除 `useAuth().workspaceId` 用于 dict 的逻辑
- `listDicts({ page, page_size, ... })` 无 workspaceId
- `listDictItems(activeDict.id)` 等同理
- `queryClient.invalidateQueries({ queryKey: dictQueryKeys.all() })`
- 增加 `forbidden` 状态（参考 `TenantsPage.tsx`）：首屏 `listDicts` 若 `ApiError.code === 'auth.forbidden'` 显示 `Result status="403"`

- [ ] **Step 2: ModelProvidersPage**

```typescript
const dicts = await listAllDicts()
// ...
listDictItems(p.id)
```

- [ ] **Step 3: 前端 build**

Run: `cd frontend && npm run build`  
Expected: 编译成功

---

### Task 10: 全量验证与文档

**Files:**
- Modify: `docs/superpowers/specs/2026-06-12-dict-global-design.md`（状态 → 已实现）

- [ ] **Step 1: 后端全量 pytest**

Run: `cd backend && pytest -q`  
Expected: 全部 PASS

- [ ] **Step 2: 搜索残留旧路径**

Run: `rg "/workspaces/.*/dicts" frontend backend`  
Expected: 无匹配

- [ ] **Step 3: 更新 spec 状态**

`2026-06-12-dict-global-design.md` 首行状态改为：**已实现（2026-06-12）**

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 删 workspace_id + 全局唯一 dict_code | Task 1 |
| is_any_workspace_member + 超管兜底 | Task 2 |
| Repository/Service 全局化 | Task 3–4 |
| `/sys/dicts` + 读写分权 | Task 5 |
| API 测试 | Task 6 |
| translate / model_provider / user 调用方 | Task 7 |
| 前端 API + hook + 页面 | Task 8–9 |
| 旧路径不保留 | Task 5, 10 |
| 文档回填 | Task 10 |

## Self-Review Notes

- 用户模块 `GET /workspaces/{id}/users/meta/departments` **路径不变**；仅 service 读全局 `SYS_DEPARTMENT`（Task 7 Step 4）。
- `DictText` 等仅依赖 `useDictItemTree` 的组件无需单独改文件。
- 全局 seed：表已空，实现时可在 Task 7 保留 `ensure_translate_status_dicts` idempotent；其余字典由超管在管理页录入或后续 seed SQL（YAGNI：本计划不强制新增 seed 文件，除非测试需要）。
