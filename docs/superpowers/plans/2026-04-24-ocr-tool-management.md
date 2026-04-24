# OCR 工具管理（sys_ocr_tool + 管理端 UI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `workspace_id` 隔离下实现 `sys_ocr_tool` 的后端 CRUD 与管理端页面，数据源仅为服务端 API，并可选从旧 localStorage 导入一条记录。

**Architecture:** 按 `app/tool/ocr` 垂直切片：`domain/db` 放 ORM，`infrastructure` 放仓储访问，`service` 编排用例，`api` 暴露 FastAPI + Pydantic；路由前缀 `/workspaces/{workspace_id}/ocr-tools`，鉴权复用 `require_workspace_member`。列表 DTO 不返回密钥明文，仅 `has_api_key` / `has_password`。PATCH 使用「仅更新请求体中出现的字段」语义（`exclude_unset=True`）；要对密钥字段清空时显式传 JSON `null`。

**Tech Stack:** FastAPI、SQLAlchemy 2.0 async、Alembic、PostgreSQL、pytest + httpx `AsyncClient`、React + Ant Design + 现有 `apiJson` / `AuthContext.workspaceId`。

**依据 spec：** [`docs/superpowers/specs/2026-04-24-ocr-tool-management-design.md`](../../specs/2026-04-24-ocr-tool-management-design.md)

---

## 将创建 / 修改的文件一览

| 路径 | 动作 | 职责 |
|------|------|------|
| `backend/alembic/versions/d91e4f2a8c00_sys_ocr_tool.py` | 创建 | 新建 `sys_ocr_tool` 表（含 `workspace_id`、索引、FK） |
| `backend/sql/schema_postgresql.sql` | 修改 | 与 Alembic 目标表结构一致（替换或增补现有无 `workspace_id` 片段） |
| `backend/app/tool/ocr/domain/db/models.py` | 创建 | `SysOcrTool` ORM |
| `backend/app/infrastructure/db/bootstrap.py` | 修改 | `_import_models()` 注册 `SysOcrTool` |
| `backend/app/tool/ocr/infrastructure/repository.py` | 创建 | 按 `workspace_id` 查询/写入 |
| `backend/app/tool/ocr/service/ocr_tool_service.py` | 创建 | CRUD + 404/403 边界（403 由 deps 处理） |
| `backend/app/tool/ocr/api/schemas.py` | 创建 | 请求/响应 Pydantic |
| `backend/app/tool/ocr/api/router.py` | 创建 | 五个端点 |
| `backend/app/api/router.py` | 修改 | `include_router` |
| `backend/tests/test_ocr_tools_api.py` | 创建 | 集成测试 |
| `minerva-ui/src/api/ocrTools.ts` | 创建 | 类型与 `apiJson` 封装 |
| `minerva-ui/src/features/settings/OcrSettingsPage.tsx` | 修改 | 表格 + 表单 + 可选导入 |
| `minerva-ui/src/i18n/locales/en.json` | 修改 | 文案 |
| `minerva-ui/src/i18n/locales/zh-CN.json` | 修改 | 文案 |

---

### Task 1: Alembic 迁移与 `schema_postgresql.sql`

**Files:**
- Create: `backend/alembic/versions/d91e4f2a8c00_sys_ocr_tool.py`
- Modify: `backend/sql/schema_postgresql.sql`（`sys_ocr_tool` 段）

- [ ] **Step 1: 确认当前 head**

Run:

```bash
cd backend
alembic heads
```

Expected: 单行 `c4f8a91b2d10 (head)`。

- [ ] **Step 2: 新增 revision 文件（若本机 revision id 冲突，改用 `alembic revision` 生成新 id，并全文替换本任务中的 id）**

Create `backend/alembic/versions/d91e4f2a8c00_sys_ocr_tool.py`:

```python
"""sys_ocr_tool with workspace_id

Revision ID: d91e4f2a8c00
Revises: c4f8a91b2d10
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d91e4f2a8c00"
down_revision: Union[str, Sequence[str], None] = "c4f8a91b2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sys_ocr_tool",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=128), nullable=False),
        sa.Column("auth_type", sa.String(length=64), nullable=True),
        sa.Column("user_name", sa.String(length=64), nullable=True),
        sa.Column("user_passwd", sa.String(length=128), nullable=True),
        sa.Column("api_key", sa.String(length=128), nullable=True),
        sa.Column("remark", sa.String(length=128), nullable=True),
        sa.Column("create_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("update_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="sys_ocr_tool_pk"),
    )
    op.create_index(
        op.f("ix_sys_ocr_tool_workspace_id"),
        "sys_ocr_tool",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_ocr_tool_workspace_id"), table_name="sys_ocr_tool")
    op.drop_table("sys_ocr_tool")
```

- [ ] **Step 3: 更新 `schema_postgresql.sql`**

将文件中现有 `CREATE TABLE public.sys_ocr_tool` 块替换为与上表一致的定义（列名、长度、FK、`ON DELETE CASCADE`、主键名 `sys_ocr_tool_pk`、索引 `ix_sys_ocr_tool_workspace_id`）；保留或同步 `COMMENT ON` 语句，并为 `workspace_id` 增加列注释。

- [ ] **Step 4: 本地升级验证**

Run:

```bash
cd backend
alembic upgrade head
```

Expected: 无报错；数据库中出现 `sys_ocr_tool`。

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/d91e4f2a8c00_sys_ocr_tool.py backend/sql/schema_postgresql.sql
git commit -m "chore(db): add sys_ocr_tool with workspace_id"
```

---

### Task 2: ORM 模型与 bootstrap 注册

**Files:**
- Create: `backend/app/tool/ocr/domain/db/models.py`
- Modify: `backend/app/infrastructure/db/bootstrap.py`（函数 `_import_models`）

- [ ] **Step 1: 编写 ORM**

Create `backend/app/tool/ocr/domain/db/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SysOcrTool(Base):
    __tablename__ = "sys_ocr_tool"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(128), nullable=False)
    auth_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_passwd: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: 注册模型**

在 `backend/app/infrastructure/db/bootstrap.py` 的 `_import_models` 内追加：

```python
def _import_models() -> None:
    import app.domain.identity.models  # noqa: F401
    import app.tool.ocr.domain.db.models  # noqa: F401
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/tool/ocr/domain/db/models.py backend/app/infrastructure/db/bootstrap.py
git commit -m "feat(ocr): add SysOcrTool ORM and register in bootstrap"
```

---

### Task 3: 仓储层

**Files:**
- Create: `backend/app/tool/ocr/infrastructure/repository.py`

- [ ] **Step 1: 实现仓储函数**

Create `backend/app/tool/ocr/infrastructure/repository.py`:

```python
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tool.ocr.domain.db.models import SysOcrTool


async def list_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysOcrTool]:
    r = await session.execute(
        select(SysOcrTool)
        .where(SysOcrTool.workspace_id == workspace_id)
        .order_by(SysOcrTool.create_at.desc())
    )
    return r.scalars().all()


async def get_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID, tool_id: uuid.UUID
) -> SysOcrTool | None:
    r = await session.execute(
        select(SysOcrTool).where(
            SysOcrTool.id == tool_id,
            SysOcrTool.workspace_id == workspace_id,
        )
    )
    return r.scalar_one_or_none()


async def add(session: AsyncSession, row: SysOcrTool) -> SysOcrTool:
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_row(session: AsyncSession, row: SysOcrTool) -> None:
    await session.delete(row)
    await session.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/tool/ocr/infrastructure/repository.py
git commit -m "feat(ocr): add SysOcrTool repository"
```

---

### Task 4: 应用服务（CRUD）

**Files:**
- Create: `backend/app/tool/ocr/service/ocr_tool_service.py`

- [ ] **Step 1: 实现服务**

Create `backend/app/tool/ocr/service/ocr_tool_service.py`（`datetime` 使用 UTC；`update_at` 在 create/update 时写入）:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.tool.ocr.domain.db.models import SysOcrTool
from app.tool.ocr.infrastructure import repository as repo


def _now() -> datetime:
    return datetime.now(UTC)


async def list_tools(session: AsyncSession, *, workspace_id: uuid.UUID):
    return await repo.list_for_workspace(session, workspace_id=workspace_id)


async def get_tool(
    session: AsyncSession, *, workspace_id: uuid.UUID, tool_id: uuid.UUID
) -> SysOcrTool:
    row = await repo.get_for_workspace(session, workspace_id=workspace_id, tool_id=tool_id)
    if row is None:
        raise AppError("ocr_tool.not_found", "OCR tool not found", 404)
    return row


async def create_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    url: str,
    auth_type: str | None,
    user_name: str | None,
    user_passwd: str | None,
    api_key: str | None,
    remark: str | None,
) -> SysOcrTool:
    now = _now()
    row = SysOcrTool(
        workspace_id=workspace_id,
        name=name.strip(),
        url=url.strip(),
        auth_type=auth_type,
        user_name=user_name,
        user_passwd=user_passwd,
        api_key=api_key,
        remark=remark,
        create_at=now,
        update_at=now,
    )
    return await repo.add(session, row)


async def update_tool(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysOcrTool:
    row = await get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
    for key in patch:
        setattr(row, key, patch[key])
    row.update_at = _now()
    await session.commit()
    await session.refresh(row)
    return row


async def delete_tool(
    session: AsyncSession, *, workspace_id: uuid.UUID, tool_id: uuid.UUID
) -> None:
    row = await get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
    await repo.delete_row(session, row)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/tool/ocr/service/ocr_tool_service.py
git commit -m "feat(ocr): add OCR tool CRUD service"
```

---

### Task 5: Pydantic 与路由

**Files:**
- Create: `backend/app/tool/ocr/api/schemas.py`
- Create: `backend/app/tool/ocr/api/router.py`

- [ ] **Step 1: Schemas**

Create `backend/app/tool/ocr/api/schemas.py`:

```python
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OcrAuthType(str, Enum):
    none = "none"
    basic = "basic"
    api_key = "api_key"


class OcrToolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=128)
    auth_type: OcrAuthType | None = None
    user_name: Optional[str] = Field(default=None, max_length=64)
    user_passwd: Optional[str] = Field(default=None, max_length=128)
    api_key: Optional[str] = Field(default=None, max_length=128)
    remark: Optional[str] = Field(default=None, max_length=128)


class OcrToolPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    url: Optional[str] = Field(default=None, min_length=1, max_length=128)
    auth_type: Optional[OcrAuthType] = None
    user_name: Optional[str] = Field(default=None, max_length=64)
    user_passwd: Optional[str | None] = None
    api_key: Optional[str | None] = None
    remark: Optional[str] = Field(default=None, max_length=128)


class OcrToolListItem(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    auth_type: Optional[str]
    user_name: Optional[str]
    remark: Optional[str]
    has_api_key: bool
    has_password: bool
    create_at: Optional[str] = None
    update_at: Optional[str] = None

    model_config = {"from_attributes": False}


class OcrToolDetail(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    url: str
    auth_type: Optional[str]
    user_name: Optional[str]
    user_passwd: Optional[str]
    api_key: Optional[str]
    remark: Optional[str]
    create_at: Optional[str] = None
    update_at: Optional[str] = None
```

说明：`OcrToolPatch` 中 `user_passwd` / `api_key` 使用 `Optional[str | None]` 以便区分「未传」与「传 null 清空」在路由层用 `model_dump(exclude_unset=True)` + 单独处理 `null`。

- [ ] **Step 2: Router**

Create `backend/app/tool/ocr/api/router.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.domain.identity.models import User
from app.tool.ocr.api import schemas
from app.tool.ocr.domain.db.models import SysOcrTool
from app.tool.ocr.service import ocr_tool_service

router = APIRouter(prefix="/workspaces/{workspace_id}/ocr-tools", tags=["ocr-tools"])


def _dt_iso(v: datetime | None) -> str | None:
    if v is None:
        return None
    return v.isoformat()


def _to_list_item(row: SysOcrTool) -> schemas.OcrToolListItem:
    return schemas.OcrToolListItem(
        id=row.id,
        name=row.name,
        url=row.url,
        auth_type=row.auth_type,
        user_name=row.user_name,
        remark=row.remark,
        has_api_key=bool(row.api_key),
        has_password=bool(row.user_passwd),
        create_at=_dt_iso(row.create_at),
        update_at=_dt_iso(row.update_at),
    )


def _to_detail(row: SysOcrTool) -> schemas.OcrToolDetail:
    return schemas.OcrToolDetail(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        url=row.url,
        auth_type=row.auth_type,
        user_name=row.user_name,
        user_passwd=row.user_passwd,
        api_key=row.api_key,
        remark=row.remark,
        create_at=_dt_iso(row.create_at),
        update_at=_dt_iso(row.update_at),
    )


def _patch_to_column_updates(body: schemas.OcrToolPatch) -> dict[str, Any]:
    raw = body.model_dump(exclude_unset=True)
    out: dict[str, Any] = {}
    if "name" in raw:
        out["name"] = str(raw["name"]).strip()
    if "url" in raw:
        out["url"] = str(raw["url"]).strip()
    if "auth_type" in raw and raw["auth_type"] is not None:
        out["auth_type"] = raw["auth_type"].value
    elif "auth_type" in raw and raw["auth_type"] is None:
        out["auth_type"] = None
    if "user_name" in raw:
        out["user_name"] = raw["user_name"]
    if "remark" in raw:
        out["remark"] = raw["remark"]
    if "user_passwd" in raw:
        out["user_passwd"] = raw["user_passwd"]
    if "api_key" in raw:
        out["api_key"] = raw["api_key"]
    return out


@router.get("", response_model=list[schemas.OcrToolListItem])
async def list_ocr_tools(
    workspace_id: uuid.UUID,
    _ws: uuid.UUID = Depends(require_workspace_member),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[schemas.OcrToolListItem]:
    rows = await ocr_tool_service.list_tools(session, workspace_id=workspace_id)
    return [_to_list_item(r) for r in rows]


@router.post("", response_model=schemas.OcrToolDetail, status_code=201)
async def create_ocr_tool(
    workspace_id: uuid.UUID,
    body: schemas.OcrToolCreate,
    _ws: uuid.UUID = Depends(require_workspace_member),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.OcrToolDetail:
    row = await ocr_tool_service.create_tool(
        session,
        workspace_id=workspace_id,
        name=body.name,
        url=body.url,
        auth_type=body.auth_type.value if body.auth_type is not None else None,
        user_name=body.user_name,
        user_passwd=body.user_passwd,
        api_key=body.api_key,
        remark=body.remark,
    )
    return _to_detail(row)


@router.get("/{tool_id}", response_model=schemas.OcrToolDetail)
async def get_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    _ws: uuid.UUID = Depends(require_workspace_member),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.OcrToolDetail:
    row = await ocr_tool_service.get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
    return _to_detail(row)


@router.patch("/{tool_id}", response_model=schemas.OcrToolDetail)
async def patch_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: schemas.OcrToolPatch,
    _ws: uuid.UUID = Depends(require_workspace_member),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> schemas.OcrToolDetail:
    updates = _patch_to_column_updates(body)
    if not updates:
        row = await ocr_tool_service.get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
        return _to_detail(row)
    row = await ocr_tool_service.update_tool(
        session,
        workspace_id=workspace_id,
        tool_id=tool_id,
        patch=updates,
    )
    return _to_detail(row)


@router.delete("/{tool_id}", status_code=204)
async def delete_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    _ws: uuid.UUID = Depends(require_workspace_member),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await ocr_tool_service.delete_tool(session, workspace_id=workspace_id, tool_id=tool_id)
```

实现时注意：`OcrToolCreate` 若 `auth_type` 可为空，需允许 `None` 写入 DB。`require_workspace_member` 与 `get_current_user` 顺序：FastAPI 会先解析路径参数；确保 `get_current_user` 仍能拿到 Bearer（与现有 `deps` 一致）。

若 `OcrToolPatch` 的 `auth_type` 需要支持清空，可在 Pydantic 用 `Optional[OcrAuthType] = None` 并区分：仅当 key 在 `model_dump(exclude_unset=True)` 中才更新（上面 `_patch_to_column_updates` 已处理 `None` 清空）。

- [ ] **Step 3: 修正 schema / 路由中的小问题并通过 import**

本地执行：

```bash
cd backend
python -c "from app.tool.ocr.api.router import router; print(router.prefix)"
```

Expected: 打印 `/workspaces/{workspace_id}/ocr-tools`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/tool/ocr/api/schemas.py backend/app/tool/ocr/api/router.py
git commit -m "feat(ocr): add OCR tools REST API"
```

---

### Task 6: 挂载总路由

**Files:**
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: include_router**

在 `backend/app/api/router.py` 增加：

```python
from app.tool.ocr.api.router import router as ocr_tools_router
# ...
api.include_router(ocr_tools_router)
```

保持与 `health` / `auth` 相同的无全局 `/api/v1` 前缀（与 spec 一致）。

- [ ] **Step 2: 手动烟测**

启动应用后：

```bash
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/workspaces/00000000-0000-0000-0000-000000000001/ocr-tools
```

Expected: `401`（无 token）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/router.py
git commit -m "feat(api): mount OCR tools router"
```

---

### Task 7: 集成测试

**Files:**
- Create: `backend/tests/test_ocr_tools_api.py`

- [ ] **Step 1: 编写测试**

Create `backend/tests/test_ocr_tools_api.py`:

```python
from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


def _wid_from_access(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


@pytest.mark.asyncio
async def test_ocr_tools_crud_and_isolation() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        e1 = f"a{uuid.uuid4().hex}@example.com"
        e2 = f"b{uuid.uuid4().hex}@example.com"
        pw = "secret1234"

        r1 = await ac.post("/auth/register", json={"email": e1, "password": pw})
        assert r1.status_code == 201, r1.text
        t1 = r1.json()["access_token"]
        ws1 = _wid_from_access(t1)

        r2 = await ac.post("/auth/register", json={"email": e2, "password": pw})
        assert r2.status_code == 201, r2.text
        t2 = r2.json()["access_token"]

        h1 = {"Authorization": f"Bearer {t1}"}
        h2 = {"Authorization": f"Bearer {t2}"}

        empty = await ac.get(f"/workspaces/{ws1}/ocr-tools", headers=h1)
        assert empty.status_code == 200
        assert empty.json() == []

        create = await ac.post(
            f"/workspaces/{ws1}/ocr-tools",
            headers=h1,
            json={
                "name": "paddle",
                "url": "http://ocr.example/v1",
                "auth_type": "api_key",
                "api_key": "sekret",
            },
        )
        assert create.status_code == 201, create.text
        tid = create.json()["id"]

        forbidden = await ac.get(f"/workspaces/{ws1}/ocr-tools", headers=h2)
        assert forbidden.status_code == 403

        lst = await ac.get(f"/workspaces/{ws1}/ocr-tools", headers=h1)
        assert lst.status_code == 200
        body = lst.json()
        assert len(body) == 1
        assert body[0]["has_api_key"] is True
        assert body[0].get("api_key") is None
        assert body[0].get("user_passwd") is None

        other_ws = str(uuid.uuid4())
        not_member = await ac.get(f"/workspaces/{other_ws}/ocr-tools", headers=h1)
        assert not_member.status_code == 403

        leak = await ac.get(f"/workspaces/{other_ws}/ocr-tools/{tid}", headers=h1)
        assert leak.status_code == 403

        wrong_ws = str(uuid.uuid4())
        not_found = await ac.get(f"/workspaces/{ws1}/ocr-tools/{wrong_ws}", headers=h1)
        assert not_found.status_code == 404

        detail = await ac.get(f"/workspaces/{ws1}/ocr-tools/{tid}", headers=h1)
        assert detail.status_code == 200
        assert detail.json()["api_key"] == "sekret"

        patch = await ac.patch(
            f"/workspaces/{ws1}/ocr-tools/{tid}",
            headers=h1,
            json={"name": "paddle2", "api_key": None},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["name"] == "paddle2"
        assert patch.json()["api_key"] is None

        lst2 = await ac.get(f"/workspaces/{ws1}/ocr-tools", headers=h1)
        assert lst2.json()[0]["has_api_key"] is False

        del_r = await ac.delete(f"/workspaces/{ws1}/ocr-tools/{tid}", headers=h1)
        assert del_r.status_code == 204

        gone = await ac.get(f"/workspaces/{ws1}/ocr-tools/{tid}", headers=h1)
        assert gone.status_code == 404
```

注意：测试依赖本机 PostgreSQL 与已执行 `alembic upgrade head`（或启动时 `AUTO_CREATE_TABLES` 已创建新表）。`other_ws` 使用随机 UUID 时用户不是成员 → `require_workspace_member` 应 403；`wrong_ws` 作为 tool_id 时若格式合法但无此行 → 404。

修正：`not_found` 一行应使用**不存在的 tool_id**，不是 workspace id。将 `wrong_ws` 改为 `fake_tid = str(uuid.uuid4())`，请求 `GET /workspaces/{ws1}/ocr-tools/{fake_tid}`。

- [ ] **Step 2: 运行测试**

Run:

```bash
cd backend
pytest tests/test_ocr_tools_api.py -v
```

Expected: 全部 PASSED。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_ocr_tools_api.py
git commit -m "test(ocr): add OCR tools API integration tests"
```

---

### Task 8: 前端 API 客户端

**Files:**
- Create: `minerva-ui/src/api/ocrTools.ts`

- [ ] **Step 1: 实现客户端**

Create `minerva-ui/src/api/ocrTools.ts`（路径与字段与后端一致；`PATCH` 用 `JSON.stringify` 以支持 `null` 清空密钥）:

```typescript
import { apiJson } from '@/api/client'

export type OcrAuthType = 'none' | 'basic' | 'api_key'

export type OcrToolListItem = {
  id: string
  name: string
  url: string
  auth_type: string | null
  user_name: string | null
  remark: string | null
  has_api_key: boolean
  has_password: boolean
  create_at: string | null
  update_at: string | null
}

export type OcrToolDetail = {
  id: string
  workspace_id: string
  name: string
  url: string
  auth_type: string | null
  user_name: string | null
  user_passwd: string | null
  api_key: string | null
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type OcrToolCreateBody = {
  name: string
  url: string
  auth_type?: OcrAuthType | null
  user_name?: string | null
  user_passwd?: string | null
  api_key?: string | null
  remark?: string | null
}

export type OcrToolPatchBody = Partial<{
  name: string
  url: string
  auth_type: OcrAuthType | null
  user_name: string | null
  user_passwd: string | null
  api_key: string | null
  remark: string | null
}>

export function listOcrTools(workspaceId: string) {
  return apiJson<OcrToolListItem[]>(`/workspaces/${workspaceId}/ocr-tools`)
}

export function createOcrTool(workspaceId: string, body: OcrToolCreateBody) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getOcrTool(workspaceId: string, toolId: string) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`)
}

export function patchOcrTool(workspaceId: string, toolId: string, body: OcrToolPatchBody) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteOcrTool(workspaceId: string, toolId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`, {
    method: 'DELETE',
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add minerva-ui/src/api/ocrTools.ts
git commit -m "feat(ui): add OCR tools API client"
```

---

### Task 9: 管理页与 i18n

**Files:**
- Modify: `minerva-ui/src/features/settings/OcrSettingsPage.tsx`
- Modify: `minerva-ui/src/i18n/locales/en.json`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`

- [ ] **Step 1: 重写页面**

将 `OcrSettingsPage` 改为：

- `useAuth().workspaceId` 为空时提示重新登录。
- `useEffect` 加载 `listOcrTools`；表格列：名称、URL、`auth_type`、备注、`update_at`；`has_api_key` / `has_password` 可用 Tag 显示「已配置」。
- 「新建」「编辑」使用 `Modal` + `Form`；字段对齐 `OcrToolCreate`；编辑时先 `getOcrTool` 回填；`auth_type` 使用 `Select`（`none` / `basic` / `api_key`）。
- 删除：`Modal.confirm` 后 `deleteOcrTool` 并刷新列表。
- **可选导入**：若 `readOcrSettings()` 存在且 `mode === 'http'` 且 `baseUrl` 非空，展示次要按钮「从本机导入」→ `createOcrTool` 映射 spec 6.1 → `write` 删除：对 `ocrSettingsStorage` 调用移除 key 的函数（在 `ocrSettingsStorage.ts` 增加 `clearOcrSettings()` 导出，内部 `removeItem`）。

- [ ] **Step 2: 文案**

在 `en.json` / `zh-CN.json` 的 `settings` 段增加键：如 `ocrToolsTitle`、`ocrToolsAdd`、`ocrToolsEdit`、`ocrToolsDeleteConfirm`、`ocrImportLocal`、`ocrImportDone`、`ocrNoWorkspace` 等；删除或改写仅适用于旧表单的键，避免死键。

- [ ] **Step 3: 构建**

Run:

```bash
cd minerva-ui
npm run build
```

Expected: 成功。

- [ ] **Step 4: Commit**

```bash
git add minerva-ui/src/features/settings/OcrSettingsPage.tsx minerva-ui/src/features/settings/ocrSettingsStorage.ts minerva-ui/src/i18n/locales/en.json minerva-ui/src/i18n/locales/zh-CN.json
git commit -m "feat(ui): OCR tools management page and i18n"
```

---

## Spec 对照自检

| Spec 章节 | 对应任务 |
|-----------|----------|
| workspace 隔离 + CRUD | Task 1–7 |
| 列表不含密钥 | Task 5 `_to_list_item` + Task 7 |
| PATCH 语义写死 | Task 5 `exclude_unset` + 显式 `null` |
| 跨 workspace 404 | Task 4 `get_tool` + Task 7（需使用另一用户的 `tool_id` 测 404 时，用 user2 的 token 请求 user1 的 `ws1` 与 `tid`：应 403 而非 404；404 用错误 `tool_id`） |
| bootstrap 注册 ORM | Task 2 |
| 前端仅 API + 可选导入 | Task 8–9 |
| 测试覆盖 403/404/CRUD | Task 7 |

**占位符扫描：** 本计划未使用 `TBD` / 空实现步骤；测试中的 `wrong_ws` 已改为「错误 `tool_id`」语义（请在 Step 1 中采用 `fake_tid` 变量名，与上文修正一致）。

**一致性：** `OcrAuthType` 枚举值与 spec `none` / `basic` / `api_key` 一致；路由前缀与 spec 一致。

---

## 执行方式（完成后由你方选择）

Plan 已保存到 [`docs/superpowers/plans/2026-04-24-ocr-tool-management.md`](./2026-04-24-ocr-tool-management.md)。

**1. Subagent-Driven（推荐）** — 每任务派生子代理，任务间人工复核，迭代快。  

**2. Inline Execution** — 本会话内按任务执行，批量变更并在检查点停顿。

你想用哪一种？
