# 文件存储本地存储 + 启用互斥 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 `sys_storage` 与设置页支持 `LOCAL` 类型及相对路径；后端启用互斥与 `resolve_active_storage`；新增 `app/local/` 提供与 S3 对齐的上传/列表/下载/删除 API；无启用项时回退 `FILE_STORAGE_LOCAL_ROOT/{workspace_id}/`。

**Architecture:** 平行模块 `app/local/`（对齐 `app/s3/`）；存储解析与互斥在 `app/sys/file_storage/service/`；路径解析使用 `resolve_file_storage_local_root()` + workspace 子目录 + 可选 `local_path`；`/s3/files` 与 `/local/files` 双轨并存，业务通过 `ActiveStorage.kind` 分支。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pathlib, pytest + pytest-asyncio, React + Ant Design。

**设计依据:** `docs/superpowers/specs/2026-06-30-file-storage-local-design.md`

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/sql/schema_postgresql.sql` | `sys_storage.local_path` 列 |
| `backend/sql/patches/2026-06-30-sys-storage-local-path.sql` | 已有库增量 DDL |
| `backend/sql/patches/2026-06-30-storge-type-local-dict-item.sql` | `STORGE_TYPE` 字典补 `LOCAL` 项 |
| `backend/app/config.py` | `file_storage_local_root`、`resolve_file_storage_local_root()` |
| `backend/.env.example`, `backend/.env.dev` | `FILE_STORAGE_LOCAL_ROOT` |
| `backend/app/sys/file_storage/domain/db/models.py` | ORM `local_path` |
| `backend/app/sys/file_storage/api/schemas.py` | 请求/响应 `local_path` |
| `backend/app/sys/file_storage/api/router.py` | 映射 `local_path` |
| `backend/app/sys/file_storage/infrastructure/repository.py` | `disable_others_for_workspace`、`get_enabled_for_workspace` |
| `backend/app/sys/file_storage/service/path_validation.py` | `local_path` 校验、`resolve_effective_local_root()` |
| `backend/app/sys/file_storage/service/storage_resolver.py` | `ActiveStorage`、`resolve_active_storage()` |
| `backend/app/sys/file_storage/service/file_storage_service.py` | LOCAL 校验、互斥、S3 字段校验分支 |
| `backend/app/s3/service/s3_file_service.py` | 仅加载 `enabled=true AND type=S3` |
| `backend/app/local/**` | 本地文件模块（api/domain/infrastructure/service） |
| `backend/app/core/api/router.py` | 挂载 local router |
| `backend/tests/test_file_storage_local_path.py` | 路径校验单元测试 |
| `backend/tests/test_storage_resolver.py` | resolver + 互斥（async DB） |
| `backend/tests/test_local_file_service.py` | gateway/service（tmp_path） |
| `frontend/src/api/fileStorage.ts` | 类型与 API 字段 |
| `frontend/src/features/file-storage/FileStoragePage.tsx` | LOCAL 表单/列表 |
| `frontend/src/i18n/locales/zh-CN.json`, `en.json` | i18n |
| `docs/superpowers/specs/2026-06-30-file-storage-local-design.md` | 实现对照回填 |

---

## Task 1: 数据库与环境变量

**Files:**
- Modify: `backend/sql/schema_postgresql.sql`
- Create: `backend/sql/patches/2026-06-30-sys-storage-local-path.sql`
- Modify: `backend/app/sys/file_storage/domain/db/models.py`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`

- [ ] **Step 1: 写失败测试（ORM 字段存在）**

创建 `backend/tests/test_file_storage_local_path.py`：

```python
from app.sys.file_storage.domain.db.models import SysStorage


def test_sys_storage_has_local_path_column() -> None:
  cols = {c.key for c in SysStorage.__table__.columns}
  assert "local_path" in cols
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_file_storage_local_path.py::test_sys_storage_has_local_path_column -v
```

Expected: FAIL（`local_path` 不在列集合中）。

- [ ] **Step 3: 实现 DDL 与 ORM**

`schema_postgresql.sql` 在 `sys_storage` 表 `bucket_name` 后增加：

```sql
local_path varchar(128) NULL,
```

并增加 `COMMENT ON COLUMN public.sys_storage.local_path IS 'LOCAL 类型相对 workspace 根的路径段';`

`patches/2026-06-30-sys-storage-local-path.sql`：

```sql
ALTER TABLE public.sys_storage
  ADD COLUMN IF NOT EXISTS local_path varchar(128) NULL;

COMMENT ON COLUMN public.sys_storage.local_path IS 'LOCAL 类型相对 workspace 根的路径段';
```

`models.py` 增加：

```python
local_path: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

`config.py` 在 `agent_files_root` 附近增加：

```python
file_storage_local_root: str = Field(
    default="",
    description="全局本地文件存储根目录；空则使用 backend/data/file-storage。",
    validation_alias=AliasChoices(
        "FILE_STORAGE_LOCAL_ROOT",
        "file_storage_local_root",
    ),
)
```

在 `resolve_agent_files_root()` 后增加：

```python
def resolve_file_storage_local_root() -> Path:
    """Return configured file storage local root, defaulting to ``backend/data/file-storage``."""
    raw = (settings.file_storage_local_root or "").strip()
    if raw:
        return Path(raw).resolve()
    return (_BACKEND_DIR / "data" / "file-storage").resolve()
```

`.env.example` / `.env.dev` 增加一行：

```
FILE_STORAGE_LOCAL_ROOT=./data/file-storage
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && pytest tests/test_file_storage_local_path.py::test_sys_storage_has_local_path_column -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sql/schema_postgresql.sql backend/sql/patches/2026-06-30-sys-storage-local-path.sql backend/app/sys/file_storage/domain/db/models.py backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_file_storage_local_path.py
git commit -m "feat(file-storage): add local_path column and FILE_STORAGE_LOCAL_ROOT"
```

---

## Task 2: 路径校验与 effective root 解析

**Files:**
- Create: `backend/app/sys/file_storage/service/path_validation.py`
- Modify: `backend/tests/test_file_storage_local_path.py`

- [ ] **Step 1: 写失败测试**

在 `test_file_storage_local_path.py` 追加：

```python
import uuid

import pytest

from app.exceptions import AppError
from app.sys.file_storage.service.path_validation import (
    normalize_local_path_segment,
    resolve_effective_local_root,
)


def test_normalize_local_path_rejects_traversal() -> None:
    with pytest.raises(AppError) as exc:
        normalize_local_path_segment("../etc")
    assert exc.value.code == "file_storage.local_path_invalid"


def test_normalize_local_path_allows_backup() -> None:
    assert normalize_local_path_segment("backup") == "backup"
    assert normalize_local_path_segment("  ") is None


def test_resolve_effective_local_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_LOCAL_ROOT", str(tmp_path))
    from importlib import reload
    import app.config as config_mod
    reload(config_mod)
    ws = uuid.uuid4()
    root = resolve_effective_local_root(workspace_id=ws, local_path="backup")
    assert root == (tmp_path / str(ws) / "backup").resolve()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/test_file_storage_local_path.py -v
```

Expected: FAIL（`ModuleNotFoundError: path_validation`）。

- [ ] **Step 3: 实现 path_validation.py**

```python
"""LOCAL storage path segment validation and workspace root resolution."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import resolve_file_storage_local_root
from app.exceptions import AppError

_LOCAL_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")


def normalize_local_path_segment(value: str | None) -> str | None:
    """Trim and validate relative local_path; blank becomes None."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if (
        trimmed.startswith("/")
        or "\\" in trimmed
        or ".." in trimmed
        or "//" in trimmed
        or not _LOCAL_PATH_PATTERN.fullmatch(trimmed)
    ):
        raise AppError(
            "file_storage.local_path_invalid",
            "Invalid local_path segment",
            422,
        )
    return trimmed


def resolve_workspace_local_root(*, workspace_id: uuid.UUID) -> Path:
    """Return ``FILE_STORAGE_LOCAL_ROOT / workspace_id``."""
    return (resolve_file_storage_local_root() / str(workspace_id)).resolve()


def resolve_effective_local_root(
    *,
    workspace_id: uuid.UUID,
    local_path: str | None,
) -> Path:
    """Return directory root for object files under one workspace LOCAL config."""
    workspace_root = resolve_workspace_local_root(workspace_id=workspace_id)
    segment = normalize_local_path_segment(local_path)
    if segment is None:
        return workspace_root
    candidate = (workspace_root / segment).resolve()
    if workspace_root not in candidate.parents and candidate != workspace_root:
        raise AppError("local.path_escape", "Resolved path escapes workspace root", 422)
    return candidate


def resolve_object_file(
    *,
    workspace_id: uuid.UUID,
    local_path: str | None,
    object_key: str,
) -> Path:
    """Map object key to absolute file path with traversal guard."""
    root = resolve_effective_local_root(workspace_id=workspace_id, local_path=local_path)
    # object_key uses POSIX separators
    candidate = (root / Path(object_key)).resolve()
    if root not in candidate.parents and candidate != root:
        raise AppError("local.path_escape", "Object key escapes storage root", 422)
    return candidate
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && pytest tests/test_file_storage_local_path.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/file_storage/service/path_validation.py backend/tests/test_file_storage_local_path.py
git commit -m "feat(file-storage): add local path validation and root resolution"
```

---

## Task 3: ActiveStorage resolver 与 repository 互斥查询

**Files:**
- Create: `backend/app/sys/file_storage/service/storage_resolver.py`
- Modify: `backend/app/sys/file_storage/infrastructure/repository.py`
- Create: `backend/tests/test_storage_resolver.py`

- [ ] **Step 1: 写失败测试（纯逻辑，mock session）**

```python
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.sys.file_storage.domain.db.models import SysStorage
from app.sys.file_storage.service.storage_resolver import resolve_active_storage


@dataclass
class _FakeResult:
    value: SysStorage | None

    def scalar_one_or_none(self) -> SysStorage | None:
        return self.value


@pytest.mark.asyncio
async def test_resolve_default_local_when_no_enabled_row() -> None:
    session = AsyncMock()
    session.execute.return_value = _FakeResult(None)
    active = await resolve_active_storage(session, workspace_id=uuid.uuid4())
    assert active.kind == "DEFAULT_LOCAL"
    assert active.storage_id is None
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && pytest tests/test_storage_resolver.py::test_resolve_default_local_when_no_enabled_row -v
```

- [ ] **Step 3: 实现 repository 与 resolver**

`repository.py` 追加：

```python
async def get_enabled_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> SysStorage | None:
    result = await session.execute(
        select(SysStorage).where(
            SysStorage.workspace_id == workspace_id,
            SysStorage.enabled.is_(True),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def disable_others_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    keep_storage_id: uuid.UUID,
) -> None:
    from sqlalchemy import update
    await session.execute(
        update(SysStorage)
        .where(
            SysStorage.workspace_id == workspace_id,
            SysStorage.id != keep_storage_id,
            SysStorage.enabled.is_(True),
        )
        .values(enabled=False)
    )
```

`storage_resolver.py`：

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.file_storage.infrastructure import repository as repo

ActiveStorageKind = Literal["S3", "LOCAL", "DEFAULT_LOCAL"]


@dataclass(frozen=True)
class ActiveStorage:
    kind: ActiveStorageKind
    storage_id: uuid.UUID | None
    local_path: str | None


async def resolve_active_storage(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> ActiveStorage:
    row = await repo.get_enabled_for_workspace(session, workspace_id=workspace_id)
    if row is None:
        return ActiveStorage(kind="DEFAULT_LOCAL", storage_id=None, local_path=None)
    storage_type = (row.type or "").strip().upper()
    if storage_type == "S3":
        return ActiveStorage(kind="S3", storage_id=row.id, local_path=None)
    if storage_type == "LOCAL":
        return ActiveStorage(kind="LOCAL", storage_id=row.id, local_path=row.local_path)
    raise AppError("file_storage.type_invalid", "Enabled storage type is invalid", 422)
```

- [ ] **Step 4: 补全 resolver 测试（S3 / LOCAL）并重跑**

```bash
cd backend && pytest tests/test_storage_resolver.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/file_storage/infrastructure/repository.py backend/app/sys/file_storage/service/storage_resolver.py backend/tests/test_storage_resolver.py
git commit -m "feat(file-storage): add active storage resolver"
```

---

## Task 4: file_storage_service — LOCAL 校验与启用互斥

**Files:**
- Modify: `backend/app/sys/file_storage/service/file_storage_service.py`
- Modify: `backend/tests/test_storage_resolver.py`（或新建 integration 测试文件）

- [ ] **Step 1: 扩展 `_is_local_storage` 与 LOCAL 字段校验**

在 `file_storage_service.py` 增加：

```python
from app.sys.file_storage.service.path_validation import normalize_local_path_segment
from app.sys.file_storage.infrastructure.repository import (
    disable_others_for_workspace,
)

def _is_local_storage(storage_type: str | None) -> bool:
    return (storage_type or "").strip().upper() == "LOCAL"

async def _apply_enable_mutex(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    storage_id: uuid.UUID,
) -> None:
    await disable_others_for_workspace(
        session,
        workspace_id=workspace_id,
        keep_storage_id=storage_id,
    )
```

**create_storage** 调整要点：
- 解析 `local_path = normalize_local_path_segment(data.get("local_path"))`
- LOCAL：`auth_type` 强制 `NONE`，清空凭证字段；跳过 bucket 校验
- S3：保持现有 `_assert_auth_fields` / bucket 校验
- `session.add(row)` → `await session.flush()` → 若 `row.enabled` 则 `_apply_enable_mutex` → `commit`

**update_storage** 调整要点：
- patch 含 `local_path` 时走 `normalize_local_path_segment`
- 合并后若 `row.type` 为 LOCAL，强制 `auth_type=NONE` 并清空 S3 凭证
- 最终 `enabled=true` 时 `_apply_enable_mutex`

- [ ] **Step 2: 手动验证互斥（开发库或 pytest 集成）**

若有测试 DB，创建两条同 workspace 存储，patch 启用 A，确认 B.enabled 为 false。

- [ ] **Step 3: Commit**

```bash
git add backend/app/sys/file_storage/service/file_storage_service.py
git commit -m "feat(file-storage): LOCAL validation and enable mutex"
```

---

## Task 5: 设置 API schemas/router 扩展 local_path

**Files:**
- Modify: `backend/app/sys/file_storage/api/schemas.py`
- Modify: `backend/app/sys/file_storage/api/router.py`

- [ ] **Step 1: schemas 三处增加字段**

`FileStorageCreateIn` / `FileStoragePatchIn` / `FileStorageListItemOut` / `FileStorageDetailOut` 均增加：

```python
local_path: str | None = Field(default=None, max_length=128)
```

- [ ] **Step 2: router 映射**

`_to_list_item`、`_to_detail`、`_to_create_data` 增加 `local_path=row.local_path` / `body.local_path`。

`create_storage` service 的 data dict 增加 `"local_path": body.local_path`。

- [ ] **Step 3: 启动后端 smoke**

```bash
cd backend && python -c "from app.sys.file_storage.api.schemas import FileStorageDetailOut; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/file_storage/api/schemas.py backend/app/sys/file_storage/api/router.py
git commit -m "feat(file-storage): expose local_path in settings API"
```

---

## Task 6: 修正 S3 配置加载

**Files:**
- Modify: `backend/app/s3/service/s3_file_service.py`

- [ ] **Step 1: 修改 `_load_storage_config` 查询**

将 `where` 改为：

```python
.where(
    SysStorage.workspace_id == workspace_id,
    SysStorage.enabled.is_(True),
    sa.func.upper(SysStorage.type) == "S3",
)
.limit(1)
```

删除按 `update_at` 排序取最近一条的逻辑。

无行时仍 `raise AppError("s3.storage_not_found", ...)`。

- [ ] **Step 2: Commit**

```bash
git add backend/app/s3/service/s3_file_service.py
git commit -m "fix(s3): load only enabled S3 storage row"
```

---

## Task 7: app/local 模块 — gateway 与 service

**Files:**
- Create: `backend/app/local/__init__.py`
- Create: `backend/app/local/domain/models.py`
- Create: `backend/app/local/infrastructure/local_gateway.py`
- Create: `backend/app/local/infrastructure/download_token.py`
- Create: `backend/app/local/service/local_file_service.py`
- Create: `backend/tests/test_local_file_service.py`

- [ ] **Step 1: 写失败测试（gateway put/list/get/delete）**

```python
from pathlib import Path

from app.local.infrastructure.local_gateway import LocalGateway


def test_local_gateway_roundtrip(tmp_path: Path) -> None:
    gw = LocalGateway(root=tmp_path)
    gw.put_object(object_key="ocr/2026/06/x.txt", payload=b"hi", content_type="text/plain")
    assert gw.get_object_bytes(object_key="ocr/2026/06/x.txt") == b"hi"
    items = gw.list_objects(prefix="ocr/")
    assert len(items) == 1
    gw.delete_object(object_key="ocr/2026/06/x.txt")
    assert not gw.exists(object_key="ocr/2026/06/x.txt")
```

- [ ] **Step 2: 实现 domain models**（对齐 `app/s3/domain/models.py` 命名）

`LocalObjectItem`, `LocalListPage`, `LocalUploadResult`, `LocalDownloadRedirect`, `LocalDownloadProxy`。

- [ ] **Step 3: 实现 LocalGateway**

- `put_object(object_key, payload, content_type)` — `mkdir(parents=True)` 后写文件
- `list_objects(prefix)` — `rglob` 或遍历，返回 `LocalObjectItem` 列表，按 mtime desc
- `get_object_bytes` / `open_download_stream`
- `delete_object` / `exists`

- [ ] **Step 4: 实现 download_token.py**

使用 `settings.jwt_secret` + HMAC-SHA256 签名 payload `{workspace_id, object_key, exp}`；`create_download_token` / `verify_download_token`。

- [ ] **Step 5: 实现 LocalFileService**

- 注入 `AsyncSession`
- `_resolve_root(workspace_id)`：调用 `resolve_active_storage`；`S3` → `local.storage_not_active`；`LOCAL`/`DEFAULT_LOCAL` → `resolve_effective_local_root`
- `upload_file`：复制 S3 的 `_normalize_module_prefix`、`_build_object_key`（在 local service 内复制实现，保持 key 规则一致）
- `upload` 返回 `download_url` 为带 token 的相对路径或完整 API path（与 S3 presign 语义对齐，600s）
- `list_files` / `get_download_redirect` / `get_download_proxy` / `delete_file`

- [ ] **Step 6: 运行测试**

```bash
cd backend && pytest tests/test_local_file_service.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/local backend/tests/test_local_file_service.py
git commit -m "feat(local): add local file gateway and service"
```

---

## Task 8: local API router 与挂载

**Files:**
- Create: `backend/app/local/api/schemas.py`
- Create: `backend/app/local/api/router.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: schemas** — 复制 `app/s3/api/schemas.py` 结构，改名为 `LocalFileUploadOut` 等（字段保持一致）。

- [ ] **Step 2: router** — 复制 `app/s3/api/router.py`，替换：
- prefix → `/workspaces/{workspace_id}/local/files`
- service → `LocalFileService`
- tags → `local-files`
- download redirect 使用 local token URL

- [ ] **Step 3: 增加 token 下载端点（可选同 router）**

`GET :download` 支持 `token` query：有 token 时校验后 proxy 下载（无需重复鉴权头，用于 redirect 模式）。

- [ ] **Step 4: 挂载**

`core/api/router.py`：

```python
from app.local.api.router import router as local_files_router
# ...
api.include_router(local_files_router)
```

- [ ] **Step 5: Smoke import**

```bash
cd backend && python -c "from app.core.api.router import api; print('ok')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/local/api backend/app/core/api/router.py
git commit -m "feat(local): add workspace local files API routes"
```

---

## Task 9: 字典种子 SQL

**Files:**
- Create: `backend/sql/patches/2026-06-30-storge-type-local-dict-item.sql`

- [ ] **Step 1: 编写 patch**

对每个 workspace 的 `STORGE_TYPE` 字典插入 `LOCAL` / `本地存储`（参考 `2026-06-01-model-tag-chat-dict-item.sql` 的 `NOT EXISTS` 模式；若 `STORGE_TYPE` 为全局字典则按 `sys_dict` 实际 `workspace_id` 列调整——执行前 `SELECT dict_code FROM sys_dict WHERE dict_code='STORGE_TYPE'` 确认）。

```sql
INSERT INTO public.sys_dict_item (id, dict_uuid, code, name, parent_uuid, create_at, update_at, item_sort)
SELECT gen_random_uuid(), d.id, 'LOCAL', '本地存储', NULL,
       NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC', 10
FROM public.sys_dict d
WHERE d.dict_code = 'STORGE_TYPE'
  AND NOT EXISTS (
    SELECT 1 FROM public.sys_dict_item i
    WHERE i.dict_uuid = d.id AND i.code = 'LOCAL'
  );
```

- [ ] **Step 2: Commit**

```bash
git add backend/sql/patches/2026-06-30-storge-type-local-dict-item.sql
git commit -m "chore(sql): add LOCAL item to STORGE_TYPE dictionary"
```

---

## Task 10: 前端设置页与 i18n

**Files:**
- Modify: `frontend/src/api/fileStorage.ts`
- Modify: `frontend/src/features/file-storage/FileStoragePage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: API 类型**

所有 `FileStorage*` 类型与 body 增加 `local_path?: string | null`。

- [ ] **Step 2: 表单**

- `FileStorageFormValues` 增加 `local_path?: string`
- `showLocalPathField = (watchedStorageType ?? '').trim().toUpperCase() === 'LOCAL'`
- LOCAL 时渲染 `local_path` Input；隐藏 bucket/endpoint/auth 字段
- `toPayload`：LOCAL 时 `auth_type: 'NONE'`，`bucket_name`/`endpoint_url`/凭证为 null；附带 `local_path`

- [ ] **Step 3: 列表**

- 新增列 `settings.fileStorageLocalPath`
- `handleToggleEnabled` 成功后 `setRev(n+1)` 刷新全表（展示互斥结果），替换仅 map 当前行

- [ ] **Step 4: i18n**

`zh-CN.json`：

```json
"settings.fileStorageLocalPath": "本地路径",
"settings.fileStorageLocalPathPlaceholder": "相对 workspace 根，如 backup",
"settings.fileStorageLocalPathHint": "留空表示 workspace 根目录"
```

`en.json` 对应英文。

- [ ] **Step 5: 前端类型检查**

```bash
cd frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/fileStorage.ts frontend/src/features/file-storage/FileStoragePage.tsx frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "feat(file-storage): LOCAL type UI and local_path field"
```

---

## Task 11: Spec 回填与全量验证

**Files:**
- Modify: `docs/superpowers/specs/2026-06-30-file-storage-local-design.md`

- [ ] **Step 1: 更新 spec §10 实现对照表** — 各项标记「已实现」并填代码路径。

- [ ] **Step 2: 文首状态改为「已实现」**。

- [ ] **Step 3: 后端测试全量**

```bash
cd backend && pytest tests/test_file_storage_local_path.py tests/test_storage_resolver.py tests/test_local_file_service.py -v
```

- [ ] **Step 4: 手工验收清单**

1. 设置页创建 LOCAL + `local_path=backup`，启用后互斥关闭其他项
2. `POST .../local/files:upload` 写入 `data/file-storage/{ws}/backup/...`
3. 全部禁用后 local upload 仍成功（默认根）
4. 仅启用 S3 时 `/s3/files` 可用，`/local/files` 返回 422
5. 执行 SQL patch 后设置页类型下拉出现「本地存储」

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-30-file-storage-local-design.md
git commit -m "docs: backfill file storage local spec implementation对照"
```

---

## Spec 覆盖自检

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §3 数据模型 local_path | Task 1 |
| §3.4 FILE_STORAGE_LOCAL_ROOT | Task 1 |
| §3.5 路径解析 | Task 2 |
| §4.1–4.2 ActiveStorage / resolver | Task 3 |
| §4.3 启用互斥 | Task 4 |
| §4.4 S3 加载修正 | Task 6 |
| §5 app/local 模块 | Task 7–8 |
| §6.1 设置 API local_path | Task 5 |
| §6.2–6.3 local files API | Task 8 |
| §7 前端 | Task 10 |
| §7.3 STORGE_TYPE | Task 9 |
| §9 测试 | Task 1–3, 7, 11 |

无遗漏项。

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-06-30-file-storage-local.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做代码审查，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间设检查点

你希望用哪种方式开始实现？
