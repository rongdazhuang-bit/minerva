# Model Providers CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在设置页完成 `sys_models` 的分组视图 CRUD（按 `provider_name` 分组），并落实 workspace 隔离、owner/admin 写权限、字典校验与前后端联调。

**Architecture:** 后端沿用 `domain/service/infrastructure/api` 分层，新增 `app/sys/model_provider` 模块，读接口提供平铺与分组两种视图，写接口统一操作 `sys_models` 单表。权限在 API 层通过 workspace membership role 判定，字段合法性在 service 层通过字典数据校验。前端保持单页面实现，按供应商分组渲染模型表格与弹窗表单，所有下拉项来自字典接口。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, Alembic, pytest, React 18, Ant Design, TypeScript, i18next.

---

## Scope Check

本 plan 只覆盖一个子系统：**模型供应商管理端 CRUD**（后端 API + 前端页面 + 数据库约束对齐）。对话/任务引擎读取 `sys_models` 属于后续迭代，不在本计划实现范围。

---

## File Structure

### Backend

- Create: `backend/app/sys/model_provider/__init__.py`
- Create: `backend/app/sys/model_provider/domain/__init__.py`
- Create: `backend/app/sys/model_provider/domain/db/__init__.py`
- Create: `backend/app/sys/model_provider/domain/db/models.py`
- Create: `backend/app/sys/model_provider/infrastructure/__init__.py`
- Create: `backend/app/sys/model_provider/infrastructure/repository.py`
- Create: `backend/app/sys/model_provider/service/__init__.py`
- Create: `backend/app/sys/model_provider/service/model_provider_service.py`
- Create: `backend/app/sys/model_provider/api/__init__.py`
- Create: `backend/app/sys/model_provider/api/schemas.py`
- Create: `backend/app/sys/model_provider/api/deps.py`
- Create: `backend/app/sys/model_provider/api/router.py`
- Create: `backend/tests/test_model_providers_api.py`
- Create: `backend/alembic/versions/<generated>_sys_models_workspace_constraints.py` (由 Alembic 命令生成具体文件名)
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/infrastructure/db/bootstrap.py`
- Modify: `backend/app/domain/identity/services.py`（新增按 workspace 查询 membership role 的函数）
- Modify: `backend/app/sys/dict/service/dictionary_service.py`（新增按 dict_code 读取明细的服务函数）
- Modify: `backend/sql/schema_postgresql.sql`

### Frontend

- Create: `minerva-ui/src/api/modelProviders.ts`
- Modify: `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx`
- Modify: `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.css`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

---

### Task 1: API 骨架与首个失败测试

**Files:**
- Create: `backend/tests/test_model_providers_api.py`
- Create: `backend/app/sys/model_provider/api/router.py`
- Create: `backend/app/sys/model_provider/api/__init__.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: 写失败测试（分组列表接口）**

```python
@pytest.mark.asyncio
async def test_model_providers_grouped_empty_list() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"mp-empty-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        wid = _workspace_id_from_access_token(token)
        h = {"Authorization": f"Bearer {token}"}

        resp = await ac.get(f"/workspaces/{wid}/model-providers/grouped", headers=h)
        assert resp.status_code == 200
        assert resp.json() == []
```

- [ ] **Step 2: 运行单测并确认失败**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_providers_grouped_empty_list -v`  
Expected: FAIL，通常为 404（路由不存在）。

- [ ] **Step 3: 增加最小可用路由骨架**

```python
# backend/app/sys/model_provider/api/router.py
router = APIRouter(
    prefix="/workspaces/{workspace_id}/model-providers",
    tags=["model-providers"],
)


@router.get("/grouped", response_model=list[dict])
async def list_grouped_empty(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> list[dict]:
    return []
```

```python
# backend/app/api/router.py
from app.sys.model_provider.api.router import router as model_providers_router

api.include_router(model_providers_router)
```

- [ ] **Step 4: 再次运行单测并确认通过**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_providers_grouped_empty_list -v`  
Expected: PASS。

- [ ] **Step 5: 提交骨架改动**

```bash
git add backend/tests/test_model_providers_api.py backend/app/sys/model_provider/api/router.py backend/app/sys/model_provider/api/__init__.py backend/app/api/router.py
git commit -m "test(api): add model provider grouped route skeleton"
```

---

### Task 2: 持久化层与 CRUD 主路径（含敏感字段策略）

**Files:**
- Create: `backend/app/sys/model_provider/domain/db/models.py`
- Create: `backend/app/sys/model_provider/domain/db/__init__.py`
- Create: `backend/app/sys/model_provider/domain/__init__.py`
- Create: `backend/app/sys/model_provider/infrastructure/repository.py`
- Create: `backend/app/sys/model_provider/infrastructure/__init__.py`
- Create: `backend/app/sys/model_provider/service/model_provider_service.py`
- Create: `backend/app/sys/model_provider/service/__init__.py`
- Create: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/app/infrastructure/db/bootstrap.py`
- Modify: `backend/tests/test_model_providers_api.py`

- [ ] **Step 1: 补充失败测试（创建/列表详情/更新/删除 + 敏感字段）**

```python
@pytest.mark.asyncio
async def test_model_providers_crud_and_masked_list_fields() -> None:
    # 1) create
    # 2) list /models 中不返回 api_key/auth_passwd 明文
    # 3) get /models/{id} 返回详情
    # 4) patch 更新 model_name 与 enabled
    # 5) delete 后详情 404
```

- [ ] **Step 2: 运行该测试并确认失败**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_providers_crud_and_masked_list_fields -v`  
Expected: FAIL，错误为路由未实现或字段不匹配。

- [ ] **Step 3: 实现 ORM + repository + service + schemas + 路由**

```python
# backend/app/sys/model_provider/domain/db/models.py
class SysModel(Base):
    __tablename__ = "sys_models"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    load_balancing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false())
    # ... auth_type/endpoint_url/api_key/auth_name/auth_passwd/context_size/max_tokens_to_sample/model_config/create_at/update_at
```

```python
# backend/app/sys/model_provider/api/router.py
@router.get("/models", response_model=list[ModelProviderListItemOut])
async def list_models(...): ...

@router.post("/models", response_model=ModelProviderDetailOut, status_code=status.HTTP_201_CREATED)
async def create_model(...): ...

@router.get("/models/{model_id}", response_model=ModelProviderDetailOut)
async def get_model(...): ...

@router.patch("/models/{model_id}", response_model=ModelProviderDetailOut)
async def patch_model(...): ...

@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_model(...): ...

@router.get("/grouped", response_model=list[ModelProviderGroupOut])
async def grouped(...): ...
```

```python
# backend/app/infrastructure/db/bootstrap.py
def _import_models() -> None:
    import app.domain.identity.models  # noqa: F401
    import app.sys.dict.domain.db.models  # noqa: F401
    import app.tool.ocr.domain.db.models  # noqa: F401
    import app.sys.model_provider.domain.db.models  # noqa: F401
```

- [ ] **Step 4: 运行目标测试并确认通过**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_providers_crud_and_masked_list_fields -v`  
Expected: PASS。

- [ ] **Step 5: 提交 CRUD 主路径改动**

```bash
git add backend/app/sys/model_provider backend/app/infrastructure/db/bootstrap.py backend/tests/test_model_providers_api.py
git commit -m "feat(api): implement sys_models CRUD and grouped view"
```

---

### Task 3: 角色权限与字典校验（owner/admin 写、member 只读）

**Files:**
- Create: `backend/app/sys/model_provider/api/deps.py`
- Modify: `backend/app/domain/identity/services.py`
- Modify: `backend/app/sys/dict/service/dictionary_service.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/tests/test_model_providers_api.py`

- [ ] **Step 1: 写失败测试（member 写入 403、admin 写入成功、字典非法 422）**

```python
@pytest.mark.asyncio
async def test_model_provider_permissions_and_dict_validation() -> None:
    # owner 创建 workspace
    # 另一个用户加入该 workspace 并设为 member -> POST/PATCH/DELETE 返回 403
    # 再将角色改为 admin -> POST 成功
    # provider_name/model_type 非法值 -> 422
```

- [ ] **Step 2: 运行该测试并确认失败**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_provider_permissions_and_dict_validation -v`  
Expected: FAIL，原因通常是未区分角色或未做字典校验。

- [ ] **Step 3: 落实权限依赖与字典合法性检查**

```python
# backend/app/domain/identity/services.py
async def find_workspace_role_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> MembershipRole | None:
    r = await session.execute(
        select(WorkspaceMembership.role).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    return r.scalar_one_or_none()
```

```python
# backend/app/sys/model_provider/api/deps.py
async def require_workspace_owner_or_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    role = await find_workspace_role_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    )
    if role not in (MembershipRole.owner, MembershipRole.admin):
        raise AppError("auth.forbidden", "Only workspace owner/admin can mutate model providers", 403)
    return workspace_id
```

```python
# backend/app/sys/dict/service/dictionary_service.py
async def list_items_by_dict_code(
    session: AsyncSession, *, workspace_id: uuid.UUID, dict_code: str
) -> list[SysDictItem]:
    # 先按 workspace + dict_code 找到字典，再读取 items
```

```python
# backend/app/sys/model_provider/service/model_provider_service.py
async def validate_provider_and_type_names(...):
    provider_names = {i.name for i in await dict_service.list_items_by_dict_code(..., dict_code="MODEL_PROVIDER")}
    model_type_names = {i.name for i in await dict_service.list_items_by_dict_code(..., dict_code="MODEL_TYPE")}
    if provider_name not in provider_names:
        raise AppError("model_provider.provider_name_invalid", "provider_name must exist in MODEL_PROVIDER", 422)
    if model_type not in model_type_names:
        raise AppError("model_provider.model_type_invalid", "model_type must exist in MODEL_TYPE", 422)
```

- [ ] **Step 4: 运行权限/字典测试并确认通过**

Run: `cd backend && pytest tests/test_model_providers_api.py::test_model_provider_permissions_and_dict_validation -v`  
Expected: PASS。

- [ ] **Step 5: 提交权限与校验改动**

```bash
git add backend/app/domain/identity/services.py backend/app/sys/dict/service/dictionary_service.py backend/app/sys/model_provider/api/deps.py backend/app/sys/model_provider/service/model_provider_service.py backend/app/sys/model_provider/api/router.py backend/tests/test_model_providers_api.py
git commit -m "feat(api): enforce owner admin writes and dict-backed validation"
```

---

### Task 4: 数据库迁移与初始化 SQL 对齐

**Files:**
- Create: `backend/alembic/versions/<generated>_sys_models_workspace_constraints.py`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 写失败验证（先跑迁移检查）**

Run: `cd backend && alembic upgrade head`  
Expected: 当前可能 PASS，但尚未包含 `sys_models` 约束对齐改动，后续验证会失败（缺外键/索引/注释不一致）。

- [ ] **Step 2: 生成 Alembic revision 文件**

Run: `cd backend && alembic revision -m "sys_models workspace constraints"`  
Expected: 输出新文件路径，如 `backend/alembic/versions/xxxxxxxxxxxx_sys_models_workspace_constraints.py`。

- [ ] **Step 3: 实现迁移与 schema SQL 对齐**

```python
# backend/alembic/versions/<generated>_sys_models_workspace_constraints.py
def upgrade() -> None:
    op.create_foreign_key(
        "sys_models_workspace_id_fkey",
        "sys_models",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_sys_models_workspace_id"),
        "sys_models",
        ["workspace_id"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index(op.f("ix_sys_models_workspace_id"), table_name="sys_models")
    op.drop_constraint("sys_models_workspace_id_fkey", "sys_models", type_="foreignkey")
```

```sql
-- backend/sql/schema_postgresql.sql
ALTER TABLE public.sys_models
  ADD CONSTRAINT sys_models_workspace_id_fkey
  FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_sys_models_workspace_id ON public.sys_models (workspace_id);
```

- [ ] **Step 4: 执行迁移并验证成功**

Run: `cd backend && alembic upgrade head`  
Expected: INFO 显示升级到最新 revision，退出码 0。

- [ ] **Step 5: 提交迁移与 SQL 文件**

```bash
git add backend/alembic/versions backend/sql/schema_postgresql.sql
git commit -m "chore(db): align sys_models workspace constraints"
```

---

### Task 5: 前端 API 与分组页面 CRUD

**Files:**
- Create: `minerva-ui/src/api/modelProviders.ts`
- Modify: `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx`
- Modify: `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.css`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

- [ ] **Step 1: 先引入接口调用并触发失败构建**

```tsx
// ModelProvidersPage.tsx (先接入调用，占位函数尚未实现)
import { listModelProviderGroups } from '@/api/modelProviders'
```

Run: `cd minerva-ui && npm run build`  
Expected: FAIL，报错 `Cannot find module '@/api/modelProviders'`。

- [ ] **Step 2: 实现前端 API 客户端**

```ts
// minerva-ui/src/api/modelProviders.ts
export function listModelProviderGroups(workspaceId: string) {
  return apiJson<ModelProviderGroup[]>(`/workspaces/${workspaceId}/model-providers/grouped`)
}
export function listModelProviders(workspaceId: string) {
  return apiJson<ModelProviderListItem[]>(`/workspaces/${workspaceId}/model-providers/models`)
}
export function createModelProvider(workspaceId: string, body: ModelProviderCreateBody) { ... }
export function getModelProvider(workspaceId: string, modelId: string) { ... }
export function patchModelProvider(workspaceId: string, modelId: string, body: ModelProviderPatchBody) { ... }
export function deleteModelProvider(workspaceId: string, modelId: string) { ... }
```

- [ ] **Step 3: 完成分组 UI、字典驱动表单与权限只读态**

```tsx
// ModelProvidersPage.tsx
// 1) 读取 MODEL_PROVIDER / MODEL_TYPE 字典项
// 2) 渲染 Collapse 分组，每组内 Table
// 3) Modal 表单新增/编辑，auth_type 联动字段
// 4) member 场景隐藏/禁用写操作（以接口 403 为最终兜底）
```

```tsx
<Form.Item name="provider_name" label={t('settings.modelProviderName')} rules={[{ required: true }]}>
  <Select allowClear options={providerOptions} />
</Form.Item>
<Form.Item name="model_type" label={t('settings.modelType')} rules={[{ required: true }]}>
  <Select allowClear options={modelTypeOptions} />
</Form.Item>
<Form.Item name="context_size" label={t('settings.contextSize')}>
  <InputNumber min={1} precision={0} style={{ width: '100%' }} />
</Form.Item>
```

- [ ] **Step 4: 构建与 lint 验证**

Run: `cd minerva-ui && npm run lint`  
Expected: PASS。  

Run: `cd minerva-ui && npm run build`  
Expected: PASS。

- [ ] **Step 5: 提交前端改动**

```bash
git add minerva-ui/src/api/modelProviders.ts minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx minerva-ui/src/features/settings/model-providers/ModelProvidersPage.css minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "feat(ui): implement grouped model providers CRUD page"
```

---

### Task 6: 全量回归与交付检查

**Files:**
- Modify: `backend/tests/test_model_providers_api.py`（如需补充遗漏断言）
- Modify: `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（仅在实现偏差时回写）

- [ ] **Step 1: 跑后端目标回归测试**

Run: `cd backend && pytest tests/test_model_providers_api.py tests/test_dict_api.py tests/test_ocr_tools_api.py -v`  
Expected: PASS。

- [ ] **Step 2: 跑后端全量测试**

Run: `cd backend && pytest -v`  
Expected: PASS。

- [ ] **Step 3: 跑前端全量检查**

Run: `cd minerva-ui && npm run lint && npm run build`  
Expected: PASS。

- [ ] **Step 4: 人工验收路径检查**

Run:
1. 登录 owner/admin 账号，进入 `/app/settings/models`，验证新增/编辑/删除/分组。
2. 使用 member 账号同页验证只读与写操作 403 提示。
3. 验证跨 workspace 不可见（切换 token/workspace 后列表隔离）。

Expected: 与 spec 一致。

- [ ] **Step 5: 提交收尾变更**

```bash
git add backend/tests/test_model_providers_api.py docs/superpowers/specs/2026-04-25-model-providers-management-design.md
git commit -m "test: finalize model providers acceptance coverage"
```

---

## Self-Review

### 1) Spec coverage

- `sys_models` 单表 CRUD：Task 2
- provider 分组视图：Task 1 + Task 2 + Task 5
- owner/admin 写、member 只读：Task 3 + Task 5
- 字典约束（MODEL_PROVIDER / MODEL_TYPE）：Task 3 + Task 5
- workspace 隔离：Task 2 + Task 3 + Task 6
- 敏感字段策略：Task 2
- 不加唯一约束：Task 4（仅补外键/索引，不新增 unique）

### 2) Placeholder scan

已检查本计划，无 `TODO`/`TBD`/“后续补充”占位描述。

### 3) Type consistency

计划中统一使用：
- 后端资源：`SysModel`
- 路由前缀：`/workspaces/{workspace_id}/model-providers`
- 字段名：`provider_name`, `model_name`, `model_type`, `load_balancing_enabled`
- 字典编码：`MODEL_PROVIDER`, `MODEL_TYPE`

