# 数据字典全局化（sys_dict 去 workspace 作用域）设计说明

**日期**：2026-06-12  
**状态**：已实现（2026-06-12）  
**范围**：`sys_dict` 改为平台全局；API 统一 `/sys/dicts`；**所有**直接或间接依赖 workspace 字典的接口、Service、前端 API 与组件一并改造。  
**Supersede 部分**： [2026-04-25-dictionary-management-design.md](./2026-04-25-dictionary-management-design.md)、[2026-04-27-dict-by-code-and-query-cache-design.md](./2026-04-27-dict-by-code-and-query-cache-design.md) 中关于 workspace 隔离、URL 前缀、鉴权与 `workspace_id` 字段的约定。

**包路径说明**：Python 包名为 `app.sys`；业务代码使用 `from app.sys.dict...` 等完整限定导入。

---

## 1. 目标与成功标准

### 1.1 产品决策（已确认）

| 项 | 决策 |
|---|---|
| 数据作用域 | **全局**；全平台共用一套 `sys_dict` / `sys_dict_item` |
| 写权限（POST/PATCH/DELETE） | **仅平台超级管理员**（`sys_user.is_super_admin = true`，对齐租户管理） |
| 读权限（GET） | 已登录且为**任意 workspace 成员**；**不按 workspace 过滤**数据 |
| 读权限兜底 | **超管**即使无 workspace 成员关系也允许读（避免字典管理页 403） |
| API 路径 | 统一 **`/sys/dicts`**（对齐 `/sys/menus`、`/sys/tenants`） |
| 历史数据 | `sys_dict` 表**已清理**，无需跨 workspace 合并迁移 |

### 1.2 成功标准

- 任意 workspace 成员可 `GET /sys/dicts` 及嵌套 items 端点；非成员 403。
- 非超管写操作 403；超管可完成字典 CRUD。
- `dict_code` **全局唯一**；`dict_uuid + code` 字典内唯一不变。
- 响应体不再含 `workspace_id`。
- 前端与后端**所有**字典调用点不再传递或依赖 `workspace_id` 作数据过滤。
- 旧路径 `/workspaces/{workspace_id}/dicts` **删除**，不保留兼容层。

---

## 2. 数据模型

### 2.1 约定

- 主键 UUID；**禁止外键**；`dict_uuid` / `parent_uuid` 为逻辑引用，删除字典时在应用层删除关联 `sys_dict_item`（见 minerva-conventions）。
- 同步更新 `backend/sql/schema_postgresql.sql`。
- 已有库执行 `backend/sql/patches/2026-06-12-sys-dict-global.sql`（本项目以 SQL patch 增量迁移）。

### 2.2 表 `sys_dict`（变更后）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 不变 |
| ~~`workspace_id`~~ | — | **删除** | 不再按工作空间隔离 |
| `dict_code` | VARCHAR(64) | NOT NULL | 字典编码 |
| `dict_name` | VARCHAR(128) | NULL | 字典名称 |
| `dict_sort` | SMALLINT | NULL DEFAULT 0 | 排序 |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | 不变 |
| `update_at` | TIMESTAMPTZ | NULL | 不变 |

**索引 / 约束**：

- 删除 `uq_sys_dict_workspace_dict_code`
- 新增 `uq_sys_dict_dict_code UNIQUE (dict_code)`

### 2.3 表 `sys_dict_item`

**无结构变更**（仍通过 `dict_uuid` 关联 `sys_dict.id`）。

### 2.4 SQL patch 步骤（表已空）

```sql
ALTER TABLE public.sys_dict DROP CONSTRAINT IF EXISTS uq_sys_dict_workspace_dict_code;
ALTER TABLE public.sys_dict DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE public.sys_dict
  ADD CONSTRAINT uq_sys_dict_dict_code UNIQUE (dict_code);
```

### 2.5 ORM

- `backend/app/sys/dict/domain/db/models.py`：`SysDict` 移除 `workspace_id` 及 `(workspace_id, dict_code)` 唯一约束；类注释改为「平台全局字典分类」。

---

## 3. 后端 API 与鉴权

### 3.1 路由前缀

`APIRouter(prefix="/sys/dicts", tags=["dicts"])`

在 `app/core/api/router.py` 中挂载方式不变（`include_router(dicts_router)`）。

### 3.2 鉴权依赖

| 依赖 | 位置 | 行为 |
|------|------|------|
| `require_any_workspace_member` | `app/sys/dict/api/deps.py`（新建） | 超管 **或** `sys_workspace_user` 中至少一条成员关系 |
| `require_super_admin` | 复用 `app/sys/tenant/api/deps.py`（或抽到 `app/core/api/deps.py` 供 tenant/dict 共用） | 仅超管 |

**identity 层新增**：

- `is_any_workspace_member(session, user_id)` → `app/core/domain/identity/services.py`
- 实现：`is_super_admin_user` 为 true 时返回 true；否则 `SELECT 1 FROM sys_workspace_user WHERE user_id = ? LIMIT 1`

### 3.3 端点（与现行为对齐，去掉 workspace 路径参数）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/sys/dicts` | `require_any_workspace_member` | 分页列表；`?code=` 精确匹配 + 附带 `item_tree` |
| POST | `/sys/dicts` | `require_super_admin` | 创建 |
| PATCH | `/sys/dicts/{dict_id}` | `require_super_admin` | 部分更新 |
| DELETE | `/sys/dicts/{dict_id}` | `require_super_admin` | 删除字典及应用层级联删 items |
| GET | `/sys/dicts/{dict_id}/items` | `require_any_workspace_member` | 扁平 items 列表 |
| POST | `/sys/dicts/{dict_id}/items` | `require_super_admin` | 新建 item |
| PATCH | `/sys/dicts/{dict_id}/items/{item_id}` | `require_super_admin` | 更新 item |
| DELETE | `/sys/dicts/{dict_id}/items/{item_id}` | `require_super_admin` | 有子节点则 409 |

**404 语义**：`dict_id` / `item_id` 不存在即 404；不再校验 workspace 归属。

**排序、校验、错误码**：与现实现一致（`create_at DESC, dict_sort DESC`；唯一冲突 409；删有子节点 item 409）。

### 3.4 Schema

- `SysDictListItemOut` 等响应模型**移除** `workspace_id` 字段。

---

## 4. 后端分层改造（dict 模块）

| 文件 | 改动要点 |
|------|----------|
| `infrastructure/repository.py` | `list_dicts_for_workspace` → `list_dicts`；`get_dict_by_code_for_workspace` → `get_dict_by_code`；`get_dict_for_workspace` → `get_dict_by_id`；所有查询去掉 `workspace_id` 条件 |
| `service/dictionary_service.py` | 全部方法签名去掉 `workspace_id`；错误文案去掉 workspace 措辞 |
| `api/router.py` | 新前缀 + 读写分权；路径参数仅 `dict_id` / `item_id` |
| `api/schemas.py` | 去掉 `workspace_id` |
| `api/deps.py` | 新建，含 `require_any_workspace_member` |

---

## 5. 后端间接调用方（必须同步）

以下模块**不暴露新 HTTP 路径**，但内部通过 `dictionary_service` 或 `dict_repo` 读写字典，须去掉 `workspace_id` 参数。

### 5.1 翻译模块

| 文件 | 现状 | 改造 |
|------|------|------|
| `app/translate/service/translate_dict_seed.py` | `ensure_translate_status_dicts(session, workspace_id=...)` 按 workspace seed | 改为 `ensure_translate_status_dicts(session)` 全局 idempotent seed |
| `app/translate/service/job_service.py` | 创建任务前 `ensure_translate_status_dicts(..., workspace_id)` | 调用全局 seed（或依赖启动时/首次读时已 seed） |
| `app/translate/api/router.py` | 某端点调用 per-workspace seed | 同上 |
| `app/translate/service/translate_llm.py` | `_assert_translate_dict(session, workspace_id)` 用 `list_items_by_dict_code(..., workspace_id, MODEL_TAG)` | 去掉 `workspace_id` |

### 5.2 模型供应商

| 文件 | 现状 | 改造 |
|------|------|------|
| `app/sys/model_provider/service/model_provider_service.py` | `_load_dict_code_set(session, workspace_id, dict_code)` | 去掉 `workspace_id`；调用方 `normalize_tags` / `validate_provider_name` 等同步改签名 |

`app/sys/model_provider/api/router.py` 中传入 `workspace_id` 给 dict 校验的调用一并更新。

### 5.3 用户 / 部门字典

| 文件 | 现状 | 改造 |
|------|------|------|
| `app/sys/user/service/user_service.py` | `get_dict_by_code_for_workspace(..., DEPARTMENT_DICT_CODE)` 三处；`list_department_tree(session, workspace_id)` | 改为全局 `get_dict_by_code`；`list_department_tree(session)` 不再要 workspace |
| `app/sys/user/api/router.py` | `GET /workspaces/{workspace_id}/users/meta/departments` 仍用 workspace 路径（用户模块 scope 不变） | **路由不变**；handler 内调 `list_department_tree(session)` 读全局 `SYS_DEPARTMENT` |

部门 item 校验逻辑：仍校验 item 属于全局 `SYS_DEPARTMENT` 字典，与 workspace 无关。

### 5.4 测试

| 文件 | 改造 |
|------|------|
| `backend/tests/test_model_provider_tags.py` | mock `_load_dict_code_set` 签名去掉 workspace_id |
| **新增** `backend/tests/test_dict_api.py` | 读：workspace 成员 200 / 非成员 403；写：超管 201 / 非超管 403 |
| **新增或扩展** `backend/tests/test_dict_service.py` | `dict_code` 全局唯一、删字典级联 items |

---

## 6. 前端改造清单

### 6.1 API 层

| 文件 | 改动 |
|------|------|
| `frontend/src/api/dicts.ts` | 所有 URL 改为 `/sys/dicts`；**所有函数去掉 `workspaceId` 首参**；`SysDictListItem` 去掉 `workspace_id` |

### 6.2 Query 缓存

| 文件 | 改动 |
|------|------|
| `frontend/src/constants/dictQueryKeys.ts` | key 不再含 `workspaceId`，如 `['dict', 'byCode', dictCode, { page, pageSize }]` |
| `frontend/src/hooks/useDictItemTree.ts` | 去掉 `useAuth().workspaceId`；`enabled: Boolean(dictCode)` |

### 6.3 组件（间接消费，随 hook/API 自动受益）

| 文件 | 说明 |
|------|------|
| `frontend/src/components/dict/DictText.tsx` | 仅用 `useDictItemTree`，**无需改签名** |
| `frontend/src/components/dict/index.ts` | 无改 |

### 6.4 管理页

| 文件 | 改动 |
|------|------|
| `frontend/src/features/settings/dictionary/DictionaryPage.tsx` | 去掉 `workspaceId` 传参；`dictQueryKeys` 更新；**非超管展示 403 Result**（对齐 `TenantsPage` 模式：首屏 API 403 时 `forbidden` 状态） |

### 6.5 业务页（显式传 workspaceId 调 dict API）

| 文件 | 改动 |
|------|------|
| `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx` | `listAllDicts` / `listDictItems` 去掉 `workspaceId` |
| `frontend/src/features/settings/ocr/OcrSettingsPage.tsx` | 仅用 `useDictItemTree`，随 hook 生效 |
| `frontend/src/features/file-storage/FileStoragePage.tsx` | 同上 |
| `frontend/src/features/file-ocr/FileOcrTaskPage.tsx` | 同上 |
| `frontend/src/features/translate/TranslatePage.tsx` | 同上 |
| `frontend/src/features/translate/TranslatePageLayoutCompare.tsx` | `DictText` 无改 |
| `frontend/src/features/rules/RulesManagementPage.tsx` | `useDictItemTree` 无改 |
| `frontend/src/features/rules/RulesPromptManagementPage.tsx` | 同上 |
| `frontend/src/features/rules/scopeTriple.ts` | 仅 type import，无 workspace 逻辑 |

### 6.6 用户模块

| 文件 | 改动 |
|------|------|
| `frontend/src/api/users.ts` | `fetchDepartmentTree(workspaceId)` → 仍请求 `/workspaces/{id}/users/meta/departments`（用户 API scope 不变）；后端返回全局部门树 |

---

## 7. Seed 与运维

### 7.1 全局字典 seed（建议 SQL 或启动脚本）

表清空后需保证业务依赖的字典存在，至少包括（按现有代码引用汇总）：

| `dict_code` | 用途 |
|-------------|------|
| `MODEL_TAG` | 模型标签校验 |
| `MODEL_PROVIDER` | 模型供应商名称 |
| `SYS_DEPARTMENT` | 用户部门 |
| `TRANSLATE_STATUS` / `TRANSLATE_SEGMENT_STATUS` | 翻译状态（translate seed） |
| `OCR_TYPE` / 认证类型等 | OCR 模块（见 OCR 页常量） |
| `STORAGE_TYPE` | 文件存储 |
| `ENG_SUBJECT_DOC` 等 | 规则模块 |

**策略**：

- 保留 `translate_dict_seed.ensure_translate_status_dicts(session)` 为全局 idempotent 函数；
- 可选：新增 `backend/sql/seeds/sys_dict_seed.sql` 或在实现计划中列出手动/脚本初始化步骤；
- **删除**所有「创建 workspace 时 seed 字典」的逻辑。

### 7.2 旧 Alembic

历史 revision `f8a2c9b01e77` 引入 workspace 作用域；新 patch 与之正交，仅对当前 schema 做减法。

---

## 8. 文档回填

| 文档 | 动作 |
|------|------|
| `2026-04-25-dictionary-management-design.md` | 文首增加 **修订说明**：workspace 作用域已由本文档 supersede |
| `2026-04-27-dict-by-code-and-query-cache-design.md` | 同上；URL 与 query key 以本文档为准 |
| 本文档 | 实现完成后状态改为「已实现」并注明日期 |

---

## 9. 非目标

- 不改变 `sys_role`、`sys_menu` 等工作空间或全局模块的现有作用域。
- 不保留 `/workspaces/{workspace_id}/dicts` 兼容路由。
- 不做跨 workspace 数据合并（表已空）。

---

## 10. 测试计划

1. **API**：成员读 200；无成员 403；超管写 201/204；普通成员写 403。
2. **唯一性**：重复 `dict_code` → 409；重复 item `code` → 409。
3. **树操作**：删有子节点 item → 409；删字典后 items 不可查。
4. **集成**：模型标签校验、用户部门校验、翻译状态展示仍正常（依赖全局字典）。
5. **前端**：`DictionaryPage` 超管可 CRUD；非超管 403；业务页 `DictText` / Select 正常显示。

---

## 11. 实现顺序建议

1. SQL patch + ORM + repository + service  
2. dict `router` + deps + schema + API 测试  
3. 后端间接调用方（translate / model_provider / user）  
4. 前端 `api/dicts.ts` + query keys + hook  
5. `DictionaryPage` + `ModelProvidersPage`  
6. 全局 seed + 文档回填 + 全量 pytest
