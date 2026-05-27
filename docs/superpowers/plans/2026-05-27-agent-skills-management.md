# Agent 技能管理（全局 skills CRUD UI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付租户 owner/admin 可用的「智能体 > 技能」管理页，直接读写 `backend/app/agent/skills/`，支持 zip 上传技能包、文件树浏览、md/py/json Monaco 编辑、保存后立即刷新 `skill_loader` 缓存。

**Architecture:** 后端 `SkillFilesService` 封装路径校验与 FS 操作；`require_tenant_owner_or_admin` 通过 workspace→tenant 鉴权；JWT 增加 `trole` claim；前端两级路由（列表→详情）+ `@monaco-editor/react` 按扩展名切换 language。

**Tech Stack:** Python 3.12 / FastAPI / pathlib / zipfile / pytest；React 18 / Ant Design 6 / Monaco Editor / Vite

**Spec:** `docs/superpowers/specs/2026-05-27-agent-skills-management-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/core/domain/identity/services.py` | `find_tenant_role_for_user` |
| `backend/app/core/api/deps.py` | `require_tenant_owner_or_admin` |
| `backend/app/core/infrastructure/security/jwt_tokens.py` | `trole` claim |
| `backend/app/core/api/routers/auth.py` | 登录/刷新时写入 `trole` |
| `backend/app/agent/infrastructure/skill_loader.py` | `invalidate_skill_cache` |
| `backend/app/agent/service/skill_files_service.py` | FS CRUD、zip 解压、校验 |
| `backend/app/agent/api/v2/schemas.py` | skills-mgmt 请求/响应模型 |
| `backend/app/agent/api/v2/skills_mgmt_router.py` | skills-mgmt 路由（新建，避免 router.py 过大） |
| `backend/app/agent/api/v2/router.py` | `include_router(skills_mgmt_router)` |
| `backend/tests/test_skill_files_service.py` | 服务层单测 |
| `backend/tests/test_skills_mgmt_api.py` | API 权限与集成测 |
| `minerva-ui/src/api/agentSkillsMgmt.ts` | 前端 API 客户端 |
| `minerva-ui/src/app/AuthContext.tsx` | `tenantRole` / `canManageTenantSkills` |
| `minerva-ui/src/features/agent/skills/*` | 列表/详情/registry 页与组件 |
| `minerva-ui/src/app/router.tsx` | 静态 `registry` 路由 + 动态 `:skillId` |
| `minerva-ui/src/i18n/locales/zh-CN.json` | 中文文案 |
| `minerva-ui/src/i18n/locales/en.json` | 英文文案 |
| `docs/agent-module-design.md` | 移除「非目标：用户上传 Skill 包」 |

---

### Task 1: 租户角色查询 + JWT `trole`

**Files:**
- Modify: `backend/app/core/domain/identity/services.py`
- Modify: `backend/app/core/infrastructure/security/jwt_tokens.py`
- Modify: `backend/app/core/api/routers/auth.py`

- [ ] **Step 1: 在 `services.py` 末尾添加**

```python
async def find_tenant_role_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> MembershipRole | None:
    """Return the user's tenant role, or None if not a member."""

    r = await session.execute(
        select(TenantMembership.role).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    return r.scalar_one_or_none()
```

（确保文件顶部 `TenantMembership` 已 import。）

- [ ] **Step 2: 修改 `create_access_token` 签名与 payload**

在 `jwt_tokens.py`：

```python
def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    workspace_role: str | None = None,
    tenant_role: str | None = None,
) -> str:
    ...
    if workspace_role:
        payload["wrole"] = workspace_role
    if tenant_role:
        payload["trole"] = tenant_role
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)
```

- [ ] **Step 3: 修改 `auth.py` 的 `_issue_tokens`**

```python
from app.core.domain.identity.models import TenantMembership

async def _issue_tokens(...) -> tuple[TokenOut, uuid.UUID]:
    ...
    wrole = r.scalar_one_or_none()
    ...
    trole_row = await session.execute(
        select(TenantMembership.role).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    trole = trole_row.scalar_one_or_none()
    access = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        workspace_role=wrole.value,
        tenant_role=trole.value if trole is not None else None,
    )
```

- [ ] **Step 4: 验证 import**

Run: `cd backend && python -c "from app.core.infrastructure.security.jwt_tokens import create_access_token; print('ok')"`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/domain/identity/services.py backend/app/core/infrastructure/security/jwt_tokens.py backend/app/core/api/routers/auth.py
git commit -m "feat(auth): add tenant role (trole) claim to access JWT"
```

---

### Task 2: `require_tenant_owner_or_admin` 依赖

**Files:**
- Modify: `backend/app/core/api/deps.py`

- [ ] **Step 1: 添加 imports**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import MembershipRole, Workspace
from app.core.domain.identity.services import find_tenant_role_for_user
from app.dependencies import get_db
```

- [ ] **Step 2: 添加依赖函数**

```python
async def require_tenant_owner_or_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Ensure user is tenant owner or admin for the workspace's tenant."""

    if not await find_workspace_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    ):
        raise AppError("auth.forbidden", "Not a member of this workspace", 403)
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("auth.forbidden", "Workspace not found", 403)
    role = await find_tenant_role_for_user(
        session, user_id=user.id, tenant_id=ws.tenant_id
    )
    if role is None:
        raise AppError("auth.forbidden", "Not a member of this tenant", 403)
    if role not in (MembershipRole.owner, MembershipRole.admin):
        raise AppError("skills.forbidden", "Only tenant owner/admin can manage skills", 403)
    return workspace_id
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/api/deps.py
git commit -m "feat(auth): add require_tenant_owner_or_admin dependency"
```

---

### Task 3: `invalidate_skill_cache`（TDD）

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Create: `backend/tests/test_skill_loader_invalidate.py`

- [ ] **Step 1: 编写失败测试**

```python
"""Tests for skill_loader cache invalidation."""

from __future__ import annotations

import sys

import pytest

from app.agent.infrastructure import skill_loader


def test_invalidate_skill_cache_clears_index(monkeypatch, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "INDEX.md").write_text(
        "# Index\n\n## 子技能列表\n\n- `alpha`：Alpha skill\n",
        encoding="utf-8",
    )
    (skills_dir / "alpha").mkdir()
    (skills_dir / "alpha" / "SKILL.md").write_text("# Alpha", encoding="utf-8")

    monkeypatch.setattr(skill_loader, "_SKILLS_ROOT", skills_dir)
    skill_loader.list_indexed_skills.cache_clear()

    assert [s.id for s in skill_loader.list_indexed_skills()] == ["alpha"]

    (skills_dir / "INDEX.md").write_text(
        "# Index\n\n## 子技能列表\n\n- `beta`：Beta skill\n",
        encoding="utf-8",
    )
    # Without invalidate, cache still returns alpha
    assert [s.id for s in skill_loader.list_indexed_skills()] == ["alpha"]

    skill_loader.invalidate_skill_cache()
    assert [s.id for s in skill_loader.list_indexed_skills()] == ["beta"]


def test_invalidate_skill_cache_evicts_tools_module(monkeypatch, tmp_path):
    mod_name = "app.agent.skills.fake_skill.tools"
    fake_mod = type(sys)("fake")
    sys.modules[mod_name] = fake_mod
    skill_loader.invalidate_skill_cache("fake_skill")
    assert mod_name not in sys.modules
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_skill_loader_invalidate.py -v`

Expected: FAIL (`invalidate_skill_cache` not defined)

- [ ] **Step 3: 在 `skill_loader.py` 实现**

```python
import sys

def invalidate_skill_cache(skill_id: str | None = None) -> bool:
    """Clear cached skill index and optionally evict imported tools module."""

    list_indexed_skills.cache_clear()
    if not skill_id:
        return True
    sid = _normalize_skill_id(skill_id)
    mod_name = f"app.agent.skills.{sid}.tools"
    sys.modules.pop(mod_name, None)
    importlib.invalidate_caches()
    return True
```

（`importlib` 已在文件顶部 import。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_skill_loader_invalidate.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/tests/test_skill_loader_invalidate.py
git commit -m "feat(agent): add invalidate_skill_cache for skills-mgmt writes"
```

---

### Task 4: `SkillFilesService` 路径校验与读写（TDD）

**Files:**
- Create: `backend/app/agent/service/skill_files_service.py`
- Create: `backend/tests/test_skill_files_service.py`

- [ ] **Step 1: 编写失败测试（路径穿越 + 读写）**

```python
"""Tests for SkillFilesService."""

from __future__ import annotations

import pytest

from app.agent.service.skill_files_service import SkillFilesService
from app.exceptions import AppError


@pytest.fixture
def svc(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "INDEX.md").write_text("# Index", encoding="utf-8")
    skill = root / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo", encoding="utf-8")
    return SkillFilesService(root=root)


def test_reject_path_traversal(svc: SkillFilesService):
    with pytest.raises(AppError) as exc:
        svc.read_text("../outside.txt")
    assert exc.value.code == "skills.path_invalid"


def test_read_write_skill_md(svc: SkillFilesService):
    content = svc.read_text("demo/SKILL.md")
    assert content == "# Demo"
    svc.write_text("demo/SKILL.md", "# Updated")
    assert svc.read_text("demo/SKILL.md") == "# Updated"


def test_reject_non_editable_extension(svc: SkillFilesService):
    (svc.root / "demo" / "data.bin").write_bytes(b"\x00")
    with pytest.raises(AppError) as exc:
        svc.write_text("demo/data.bin", "nope")
    assert exc.value.code == "skills.not_editable"


def test_validate_skill_id_reserved():
    with pytest.raises(AppError):
        SkillFilesService.validate_skill_id("registry")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_skill_files_service.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: 实现 `skill_files_service.py` 核心**

```python
"""Filesystem CRUD for global agent skill packages."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from app.agent.infrastructure.skill_loader import invalidate_skill_cache, skills_root
from app.exceptions import AppError

_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED_SKILL_IDS = frozenset({"registry"})
_EDITABLE_SUFFIXES = {".md", ".py", ".json"}
_MAX_TEXT_BYTES = 2 * 1024 * 1024


class SkillFilesService:
    """Read/write skill files under a fixed root with path confinement."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or skills_root()).resolve()

    @staticmethod
    def validate_skill_id(skill_id: str) -> str:
        sid = (skill_id or "").strip().lower()
        if not _SKILL_ID_RE.match(sid) or sid in _RESERVED_SKILL_IDS:
            raise AppError("skills.path_invalid", f"Invalid skill id: {skill_id}", 400)
        return sid

    def resolve_relative(self, rel: str) -> Path:
        raw = (rel or "").strip().replace("\\", "/").lstrip("/")
        if not raw or ".." in raw.split("/"):
            raise AppError("skills.path_invalid", "Invalid path", 400)
        target = (self.root / raw).resolve()
        if not str(target).startswith(str(self.root)):
            raise AppError("skills.path_invalid", "Path escapes skills root", 400)
        if target.is_symlink():
            raise AppError("skills.path_invalid", "Symlinks not allowed", 400)
        return target

    def read_text(self, rel: str) -> str:
        path = self.resolve_relative(rel)
        if not path.is_file():
            raise AppError("skills.not_found", "File not found", 404)
        data = path.read_bytes()
        if len(data) > _MAX_TEXT_BYTES:
            raise AppError("skills.path_invalid", "File too large", 400)
        return data.decode("utf-8")

    def write_text(self, rel: str, content: str) -> bool:
        path = self.resolve_relative(rel)
        if path.suffix.lower() not in _EDITABLE_SUFFIXES:
            raise AppError("skills.not_editable", "File type not editable", 400)
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_TEXT_BYTES:
            raise AppError("skills.path_invalid", "File too large", 400)
        if path.suffix.lower() == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise AppError("skills.json_invalid", str(e), 400) from e
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        skill_id = path.relative_to(self.root).parts[0] if path.relative_to(self.root).parts else None
        if path.name == "INDEX.md":
            invalidate_skill_cache(None)
        elif skill_id and skill_id != "INDEX.md":
            invalidate_skill_cache(skill_id if path.name == "tools.py" else None)
        else:
            invalidate_skill_cache(None)
        return True
```

（Task 5 将继续补充 `list_registry`、`build_tree`、`delete_path`、`upload_zip`。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_skill_files_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/service/skill_files_service.py backend/tests/test_skill_files_service.py
git commit -m "feat(agent): add SkillFilesService path-safe read/write"
```

---

### Task 5: zip 上传、文件树、删除

**Files:**
- Modify: `backend/app/agent/service/skill_files_service.py`
- Modify: `backend/tests/test_skill_files_service.py`

- [ ] **Step 1: 添加 zip 失败测试**

```python
import io
import zipfile

def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_upload_zip_single_root_folder(svc: SkillFilesService, tmp_path):
    z = _make_zip({
        "newskill/SKILL.md": b"# New",
        "newskill/tools.py": b"# tools",
    })
    svc.upload_skill_zip(z)
    assert (svc.root / "newskill" / "SKILL.md").is_file()


def test_upload_zip_rejects_multiple_roots(svc: SkillFilesService):
    z = _make_zip({"a/SKILL.md": b"#", "b/SKILL.md": b"#"})
    with pytest.raises(AppError) as exc:
        svc.upload_skill_zip(z)
    assert exc.value.code == "skills.zip_invalid"


def test_upload_zip_rejects_duplicate(svc: SkillFilesService):
    z = _make_zip({"demo/SKILL.md": b"#"})
    with pytest.raises(AppError) as exc:
        svc.upload_skill_zip(z)
    assert exc.value.code == "skills.duplicate"
```

- [ ] **Step 2: 实现 `upload_skill_zip`、`build_tree`、`delete_path`、`list_registry`**

`upload_skill_zip` 要点：
- 解压到 `self.root / ".tmp" / {uuid}/`
- 根级 `iterdir()` 必须恰好 1 个目录
- 目录名经 `validate_skill_id`
- 目标 `(self.root / skill_id).exists()` → 409
- 必须含 `SKILL.md`
- 跳过 `__pycache__`、`.pyc`
- `shutil.move` 后 `invalidate_skill_cache(skill_id)`

`build_tree(skill_id)` 返回嵌套 dict/list 结构供 API 序列化。

`delete_path(rel)` / `delete_skill(skill_id)` 递归删除并 `invalidate_skill_cache`。

- [ ] **Step 3: 运行全部 service 测试**

Run: `cd backend && uv run pytest tests/test_skill_files_service.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/service/skill_files_service.py backend/tests/test_skill_files_service.py
git commit -m "feat(agent): add skill zip upload, tree listing, and delete"
```

---

### Task 6: API schemas + router

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Create: `backend/app/agent/api/v2/skills_mgmt_router.py`
- Modify: `backend/app/agent/api/v2/router.py`

- [ ] **Step 1: 在 `schemas.py` 追加**

```python
class SkillRegistryItemOut(BaseModel):
    id: str
    description: str
    file_count: int


class SkillRegistryOut(BaseModel):
    skills: list[SkillRegistryItemOut]


class SkillFileTreeNodeOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    children: list["SkillFileTreeNodeOut"] = Field(default_factory=list)


class SkillFileContentOut(BaseModel):
    path: str
    content: str


class SkillFileWriteIn(BaseModel):
    content: str


class SkillWriteResultOut(BaseModel):
    path: str
    cache_reloaded: bool = True
```

- [ ] **Step 2: 创建 `skills_mgmt_router.py`**

```python
"""Skills filesystem management routes (tenant owner/admin only)."""

router = APIRouter(prefix="/skills-mgmt", tags=["agent-skills-mgmt"])

@router.get("/registry", response_model=SkillRegistryOut)
async def get_skill_registry(..., _ws=Depends(require_tenant_owner_or_admin)):
    ...

@router.get("/{skill_id}/tree", response_model=list[SkillFileTreeNodeOut])
...

@router.get("/files", response_model=SkillFileContentOut)
...

@router.put("/files", response_model=SkillWriteResultOut)
...

@router.post("/upload")
async def upload_skill_package(file: UploadFile, ...):
    ...

@router.post("/files/upload")
...

@router.get("/files/download")
async def download_skill_file(path: str, ...):
    return FileResponse(...)

@router.delete("/files")
...

@router.delete("/{skill_id}")
...
```

所有 handler 实例化 `SkillFilesService()`，捕获 `AppError` 透传。

- [ ] **Step 3: 在 `router.py` 挂载**

```python
from app.agent.api.v2.skills_mgmt_router import router as skills_mgmt_router
router.include_router(skills_mgmt_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/skills_mgmt_router.py backend/app/agent/api/v2/router.py
git commit -m "feat(agent): add skills-mgmt REST API for tenant admins"
```

---

### Task 7: API 集成测试

**Files:**
- Create: `backend/tests/test_skills_mgmt_api.py`
- Create: `backend/tests/conftest.py`（若不存在）

- [ ] **Step 1: 创建 `conftest.py` 最小 fixture**

提供 `async_client`、`test_user_tokens`（member vs tenant admin），使用临时 `skills` 目录 monkeypatch。

- [ ] **Step 2: 编写权限测试**

```python
async def test_member_get_registry_forbidden(async_client, member_headers):
    r = await async_client.get(f"/workspaces/{wid}/agent/v2/skills-mgmt/registry", headers=member_headers)
    assert r.status_code == 403


async def test_tenant_admin_upload_zip(async_client, admin_headers, tmp_skills):
    ...
    assert r.status_code == 201
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && uv run pytest tests/test_skills_mgmt_api.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_skills_mgmt_api.py
git commit -m "test(agent): add skills-mgmt API integration tests"
```

---

### Task 8: 前端 API 客户端 + AuthContext

**Files:**
- Create: `minerva-ui/src/api/agentSkillsMgmt.ts`
- Modify: `minerva-ui/src/app/AuthContext.tsx`

- [ ] **Step 1: 创建 `agentSkillsMgmt.ts`**

```typescript
import { apiJson, authFetch } from '@/api/client'
import { apiOrigin } from '@/api/config'

export type SkillRegistryItem = { id: string; description: string; file_count: number }
export type SkillFileTreeNode = {
  name: string
  path: string
  is_dir: boolean
  size?: number | null
  children?: SkillFileTreeNode[]
}

export function listSkillRegistry(workspaceId: string) {
  return apiJson<SkillRegistryOut>(`/workspaces/${workspaceId}/agent/v2/skills-mgmt/registry`)
}

export function readSkillFile(workspaceId: string, path: string) { ... }
export function writeSkillFile(workspaceId: string, path: string, content: string) { ... }
export function uploadSkillPackage(workspaceId: string, file: File) { ... }
export function deleteSkill(workspaceId: string, skillId: string) { ... }
export function deleteSkillPath(workspaceId: string, path: string) { ... }
export function downloadSkillFile(workspaceId: string, path: string): Promise<Blob> { ... }
```

- [ ] **Step 2: 扩展 `AuthContext.tsx`**

```typescript
type JwtPayload = { wid?: string; wrole?: string; trole?: string }

function readTenantRoleFromToken(access: string | null): string | null { ... }

// AuthValue 增加:
tenantRole: string | null
canManageTenantSkills: boolean  // trole === 'owner' || trole === 'admin'
```

- [ ] **Step 3: Commit**

```bash
git add minerva-ui/src/api/agentSkillsMgmt.ts minerva-ui/src/app/AuthContext.tsx
git commit -m "feat(ui): add agent skills-mgmt API client and tenant role auth"
```

---

### Task 9: Monaco 编辑器组件

**Files:**
- Modify: `minerva-ui/package.json`
- Create: `minerva-ui/src/features/agent/skills/components/SkillFileEditor.tsx`

- [ ] **Step 1: 安装依赖**

Run: `cd minerva-ui && npm install @monaco-editor/react`

- [ ] **Step 2: 实现 `SkillFileEditor`**

```tsx
import Editor from '@monaco-editor/react'

const LANG_BY_EXT: Record<string, string> = {
  '.py': 'python',
  '.md': 'markdown',
  '.json': 'json',
}

export function SkillFileEditor({ path, value, onChange, readOnly }: Props) {
  const ext = path.slice(path.lastIndexOf('.')).toLowerCase()
  const language = LANG_BY_EXT[ext] ?? 'plaintext'
  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      onChange={(v) => onChange(v ?? '')}
      options={{ readOnly, minimap: { enabled: false }, wordWrap: 'on' }}
    />
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add minerva-ui/package.json minerva-ui/package-lock.json minerva-ui/src/features/agent/skills/components/SkillFileEditor.tsx
git commit -m "feat(ui): add Monaco-based SkillFileEditor component"
```

---

### Task 10: 技能列表页 + Registry 页

**Files:**
- Create: `minerva-ui/src/features/agent/skills/AgentSkillsListPage.tsx`
- Create: `minerva-ui/src/features/agent/skills/AgentSkillRegistryPage.tsx`
- Create: `minerva-ui/src/features/agent/skills/AgentSkillsPage.css`
- Modify: `minerva-ui/src/features/agent/index.ts`
- Delete or replace: `minerva-ui/src/features/agent/AgentSkillsPage.tsx`

- [ ] **Step 1: 实现 `AgentSkillsListPage`**

- Table：`id` / `description` / `file_count` / 操作（进入、删除）
- 顶行链接「技能注册表 (INDEX.md)」→ `/app/agents/skills/registry`
- `Upload` 接受 `.zip`，`beforeUpload` 调 `uploadSkillPackage`
- 删除技能：`Popconfirm` + `deleteSkill`
- `canManageTenantSkills === false` 时隐藏 Upload/Delete，显示只读提示
- 分页 `DEFAULT_PAGE_SIZE`

- [ ] **Step 2: 实现 `AgentSkillRegistryPage`**

- 加载 `readSkillFile(workspaceId, 'INDEX.md')`
- `SkillFileEditor` + 保存按钮调 `writeSkillFile`
- 未保存离开拦截

- [ ] **Step 3: 更新 `index.ts` exports**

- [ ] **Step 4: Commit**

```bash
git add minerva-ui/src/features/agent/skills/ minerva-ui/src/features/agent/index.ts
git rm minerva-ui/src/features/agent/AgentSkillsPage.tsx
git commit -m "feat(ui): add agent skills list and INDEX registry pages"
```

---

### Task 11: 技能详情页（文件树 + 二进制面板）

**Files:**
- Create: `minerva-ui/src/features/agent/skills/AgentSkillDetailPage.tsx`
- Create: `minerva-ui/src/features/agent/skills/components/SkillFileTree.tsx`
- Create: `minerva-ui/src/features/agent/skills/components/SkillBinaryFilePanel.tsx`

- [ ] **Step 1: `SkillFileTree`**

- Ant Design `Tree`，data 来自 `getSkillTree(workspaceId, skillId)`
- `onSelect` 回调选中 path

- [ ] **Step 2: `SkillBinaryFilePanel`**

- 显示文件名、大小
- 按钮：下载（`downloadSkillFile`）、删除（`Popconfirm` + `deleteSkillPath`）、上传替换（`Upload` → `uploadSkillFile`）

- [ ] **Step 3: `AgentSkillDetailPage`**

- 左 Tree + 右 Editor/BinaryPanel
- 选中 `.md/.py/.json` → `SkillFileEditor`；md 顶栏可选「预览」Tab（`react-markdown`）
- 保存前 json 做 `JSON.parse` 客户端校验
- 面包屑 + 返回列表

- [ ] **Step 4: Commit**

```bash
git add minerva-ui/src/features/agent/skills/
git commit -m "feat(ui): add agent skill detail page with file tree and editors"
```

---

### Task 12: 路由、i18n、文档回填

**Files:**
- Modify: `minerva-ui/src/app/router.tsx`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`
- Modify: `docs/agent-module-design.md`

- [ ] **Step 1: 更新 `router.tsx`**

```tsx
import {
  AgentSkillsListPage,
  AgentSkillDetailPage,
  AgentSkillRegistryPage,
} from '@/features/agent'

// 在 agents/skills 下：
{ path: 'agents/skills', element: <AgentSkillsListPage /> },
{ path: 'agents/skills/registry', element: <AgentSkillRegistryPage /> },
{ path: 'agents/skills/:skillId', element: <AgentSkillDetailPage /> },
```

`registry` 路由必须在 `:skillId` 之前。

- [ ] **Step 2: 添加 i18n keys**

`zh-CN.json` / `en.json` 增加：
- `agents.skills.title`
- `agents.skills.upload`
- `agents.skills.registry`
- `agents.skills.enter`
- `agents.skills.deleteSkill`
- `agents.skills.deleteFile`
- `agents.skills.save`
- `agents.skills.unsaved`
- `agents.skills.readOnly`
- `agents.skills.preview`

移除或保留 `placeholders.agentsSkills`（不再使用）。

- [ ] **Step 3: 更新 `docs/agent-module-design.md` §1.4**

删除「用户上传自定义 Skill 包（仅内置 `skills/` 目录）」非目标行，改为：

```markdown
- 技能包在线管理见 [2026-05-27-agent-skills-management-design.md](superpowers/specs/2026-05-27-agent-skills-management-design.md)（租户 owner/admin，全局 `skills/` 目录）
```

- [ ] **Step 4: 构建验证**

Run: `cd minerva-ui && npm run build`

Expected: 构建成功，无 TS 错误

Run: `cd backend && uv run pytest tests/test_skill_files_service.py tests/test_skill_loader_invalidate.py tests/test_skills_mgmt_api.py -v`

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/app/router.tsx minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json docs/agent-module-design.md
git commit -m "feat(agent): wire skills-mgmt routes, i18n, and update agent module docs"
```

---

## Manual test checklist

- [ ] 租户 owner 登录 → 智能体 > 技能 → 看到技能列表
- [ ] 上传合法 zip（单根文件夹 + SKILL.md）→ 列表出现新 skill
- [ ] 上传重名 zip → 409 错误提示
- [ ] 进入 ppt → 编辑 `SKILL.md` 保存 → Agent 对话路由描述更新
- [ ] 编辑 `tools.py` 保存 → 下一次 Run 加载新工具
- [ ] 编辑 `INDEX.md`（registry 页）→ `GET /agent/v2/skills` 顺序/描述更新
- [ ] 租户 member 登录 → 写操作不可见或 403
- [ ] 删除技能 Popconfirm 生效
- [ ] json 非法保存被拦截；二进制文件仅下载/上传/删除

---

## Spec coverage self-review

| Spec 要求 | Task |
|-----------|------|
| 全局 skills 目录 CRUD | Task 4–6 |
| 租户 owner/admin 权限 | Task 1–2, 7 |
| zip 单根文件夹 + 重名 + SKILL.md | Task 5 |
| md/py/json 编辑 + 其他二进制 | Task 4, 9, 11 |
| 保存后立即清缓存 | Task 3, 4 |
| 两级 UI + registry | Task 10–12 |
| JWT trole | Task 1, 8 |
| 错误码 | Task 4–6 |
| 文档回填 | Task 12 |
| 测试 | Task 3, 4, 5, 7 |
