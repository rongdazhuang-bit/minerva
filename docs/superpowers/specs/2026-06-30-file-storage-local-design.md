# 文件存储：本地存储 + 启用互斥 + 默认兜底

**日期**：2026-06-30  
**状态**：已实现（2026-06-30，分支 `feat/file-storage-local`）  
**范围**：扩展系统设置「文件存储」支持 `LOCAL` 类型与相对路径；同一 workspace 仅允许一条启用配置（后端自动互斥）；无启用项时回退到环境变量定义的默认本地目录；新增 `app/local/` 提供与 S3 对齐的对象文件 API；保留 `/s3/files` 与 `/local/files` 双轨，业务模块通过 resolver 自行选择。

**关联文档**：`docs/superpowers/specs/2026-04-30-s3-file-storage-design.md`（S3 能力与 `sys_storage` 表）

**Minerva 约定**：无库级外键；环境变量同步 `backend/.env.example` 与 `backend/.env.dev`；删除/互斥在 service 层实现。

---

## 1. 已确认决策

| 项 | 决策 |
|----|------|
| 默认本地兜底 | 全局 `FILE_STORAGE_LOCAL_ROOT`，物理根为 `{FILE_STORAGE_LOCAL_ROOT}/{workspace_id}/` |
| 本期范围 | 设置 CRUD + 存储解析 + 完整本地文件服务（上传/列表/下载/删除） |
| LOCAL 路径语义 | `local_path` 为相对于 workspace 根的路径段；空 = workspace 根；`backup` → `.../{workspace_id}/backup/` |
| 对外 API | 双轨：`/s3/files`（仅 S3）、`/local/files`（本地）；业务模块自行分支 |
| 启用互斥 | 后端：启用一条时同事务将同 workspace 其他行 `enabled=false` |
| 推荐实现方案 | 平行模块 `app/local/`（结构对齐 `app/s3/`），`resolve_active_storage()` 供业务判断 |

---

## 2. 目标与成功标准

### 2.1 目标

1. 设置页支持创建/编辑 `type=LOCAL` 配置，可填可选相对路径 `local_path`。
2. 列表中 Switch 启用某条存储时，后端自动关闭同 workspace 其他启用项。
3. 无任何 `enabled=true` 时，本地文件 API 使用默认目录 `{FILE_STORAGE_LOCAL_ROOT}/{workspace_id}/`。
4. 新增 `app/local/`，对象 key 规则与 S3 一致：`{module_prefix}/{YYYY}/{MM}/{uuid}.{ext}`。
5. 修正 `S3FileService` 配置加载：仅使用 `enabled=true` 且 `type=S3` 的行（不再取「最近更新一条」）。
6. 提供 `resolve_active_storage(session, workspace_id)` 返回当前应使用的存储种类。

### 2.2 成功标准

- 配置并启用 LOCAL 后，文件写入 `{FILE_STORAGE_LOCAL_ROOT}/{workspace_id}/[local_path/]` 下预期路径。
- 启用 A 后 B 自动 `enabled=false`（单事务，列表刷新可见）。
- 全部禁用后，`POST/GET/DELETE .../local/files` 仍可对默认本地目录读写。
- 启用 S3 后，`/s3/files` 全链路正常；`/local/files` 在仅 S3 启用时返回明确错误（见 §6.3）。
- 设置页 LOCAL 表单项隐藏 S3 专有字段；列表展示本地路径列。

### 2.3 非目标

- 不合并 `/s3/files` 与 `/local/files` 为单一路由。
- 不实现 OSS/COS 等多云抽象。
- 不自动迁移历史 S3 对象到本地。
- 本期不强制改造 OCR、Dataset 等业务模块（仅提供 resolver 与 local API，迁移可后续迭代）。

---

## 3. 数据模型

### 3.1 `sys_storage` 变更

新增列：

| 列 | 类型 | 说明 |
|----|------|------|
| `local_path` | `varchar(128) NULL` | LOCAL 类型下相对于 workspace 根的路径段（非绝对路径） |

同步更新：

- `backend/sql/schema_postgresql.sql`
- `backend/sql/patches/` 增量脚本（若项目惯例要求）
- SQLAlchemy `SysStorage` 模型
- Pydantic `FileStorageCreateIn` / `FileStoragePatchIn` / 列表与详情 Out

### 3.2 类型字段语义

| `type` | 使用字段 | 说明 |
|--------|----------|------|
| `S3` | `bucket_name`, `endpoint_url`, `auth_*` | 与现有一致 |
| `LOCAL` | `local_path`（可选） | `auth_type` 固定 `NONE`；忽略 bucket/endpoint/凭证 |

### 3.3 LOCAL 校验规则

- `name`：必填（与现有一致）。
- `local_path`（非空时）：
  - 禁止 `..`、前导 `/`、反斜杠 `\`、连续 `//`。
  - 仅允许字符集 `[A-Za-z0-9/_-]`（与 object key 段风格一致）。
  - trim 后空串视为 `NULL`（使用 workspace 根）。
- `auth_type`：创建/更新 LOCAL 时强制为 `NONE`；`api_key` / `secret_key` / `auth_name` / `auth_passwd` 清空或不校验。
- 不要求 `bucket_name`、`endpoint_url`。

### 3.4 环境变量

| 变量 | 说明 | 示例默认值 |
|------|------|------------|
| `FILE_STORAGE_LOCAL_ROOT` | 全局本地存储根目录（相对或绝对路径） | `./data/file-storage` |

在 `app/config.py` 增加 `file_storage_local_root: str` 及 `resolve_file_storage_local_root() -> Path`（对齐 `resolve_agent_files_root()` 风格）。

**必须**同步 `backend/.env.example`、`backend/.env.dev`。

### 3.5 路径解析

```text
workspace_root = FILE_STORAGE_LOCAL_ROOT / str(workspace_id)
effective_root = workspace_root / local_path   # local_path 为空则仅为 workspace_root
object_file    = effective_root / object_key   # object_key 使用 POSIX 分隔符
```

解析后须校验 `object_file.resolve()` 位于 `workspace_root.resolve()` 之下（防目录穿越）。

---

## 4. 存储解析与启用互斥

### 4.1 `ActiveStorage` 领域类型

```python
@dataclass(frozen=True)
class ActiveStorage:
    kind: Literal["S3", "LOCAL", "DEFAULT_LOCAL"]
    storage_id: uuid.UUID | None   # DEFAULT_LOCAL 时为 None
    local_path: str | None         # 仅 LOCAL / DEFAULT_LOCAL 有意义；DEFAULT_LOCAL 为 None
```

### 4.2 `resolve_active_storage(session, workspace_id)`

1. 查询 `sys_storage`：`workspace_id` 匹配且 `enabled=true`，`LIMIT 1`（互斥保证至多一条）。
2. 若存在且 `type`（大写）为 `S3` → `kind=S3`, `storage_id=id`。
3. 若存在且 `type` 为 `LOCAL` → `kind=LOCAL`, `storage_id=id`, `local_path=row.local_path`。
4. 若不存在启用行 → `kind=DEFAULT_LOCAL`, `storage_id=None`, `local_path=None`。
5. 若存在启用行但 `type` 非 S3/LOCAL → `AppError("file_storage.type_invalid", ..., 422)`。

**位置**：`app/sys/file_storage/service/storage_resolver.py`（或 `file_storage_service.py` 内导出）。

### 4.3 启用互斥

在 `create_storage` 与 `update_storage` 中，当最终 `enabled=true` 时：

1. 同一数据库事务内执行：将该 `workspace_id` 下 **除当前行 id 外** 所有行的 `enabled` 设为 `false`。
2. 再写入/更新当前行 `enabled=true`。
3. `enabled=false` 的 patch/create 不触发互斥。

新建且 `enabled=true` 时，在 `flush` 获得 `id` 后执行互斥 SQL，再 `commit`。

### 4.4 S3 配置加载修正

`S3FileService._load_storage_config` 改为：

```sql
WHERE workspace_id = ? AND enabled = true AND upper(type) = 'S3'
LIMIT 1
```

若无匹配行 → 保持现有 `s3.storage_not_found` / `s3.storage_not_enabled` 语义（按实现择一或拆分）。

---

## 5. 本地文件模块 `app/local/`

### 5.1 目录结构

```text
backend/app/local/
  __init__.py
  api/
    router.py
    schemas.py
  domain/
    models.py
  infrastructure/
    local_gateway.py
  service/
    local_file_service.py
```

在 `app/core/api/router.py`（或现有 api 聚合处）挂载 local router。

### 5.2 `LocalFileService` 行为

与 `S3FileService` 对齐的公开方法：

- `upload_file(workspace_id, module_prefix, file_name, payload, content_type, ...)`
- `list_files(workspace_id, module_prefix?, page, page_size)`
- `download_file(workspace_id, object_key, mode)` → redirect URL 或字节流
- `delete_file(workspace_id, object_key)`

**解析根目录**：

1. 调用 `resolve_active_storage`。
2. `kind in (LOCAL, DEFAULT_LOCAL)` → 按 §3.5 计算 `effective_root`。
3. `kind == S3` → `AppError("local.storage_not_active", "Local storage is not active", 422)`。

首次写入前 `mkdir(parents=True, exist_ok=True)`。

### 5.3 `local_gateway.py`

封装 pathlib 操作：`put_object`、`list_objects`（前缀过滤 + 分页）、`get_object`、`delete_object`、`exists`。列表按文件 `mtime` 降序；`total` 为匹配前缀的文件数。

### 5.4 Object key

复用与 S3 相同规则（可从 `s3_file_service._build_object_key` 抽到共享函数，或 local 模块内复制同一实现以保持本期范围可控）：

`{module_prefix}/{YYYY}/{MM}/{uuid}.{ext}`

`module_prefix` / `object_key` 校验规则与 S3 一致（禁止 `..`、首尾 `/` 等）。

---

## 6. API 设计

### 6.1 文件存储设置（已有，扩展）

前缀：`/workspaces/{workspace_id}/file-storages`

- Create/Patch 请求体增加可选 `local_path`。
- 响应列表/详情增加 `local_path` 字段。

### 6.2 本地文件 API（新增）

前缀：`/workspaces/{workspace_id}/local/files`  
鉴权：`get_current_user` + `require_workspace_member`（与 S3 一致）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `:upload` | Query: `module_prefix`；multipart `file` |
| `GET` | `` | Query: `module_prefix?`, `page`, `page_size` |
| `GET` | `:download` | Query: `object_key`, `mode=redirect\|proxy`（默认 `redirect`） |
| `DELETE` | `` | Body: `{ "object_key": "..." }` |

响应字段与 `app/s3/api/schemas.py` 对齐（`object_key`, `file_name`, `content_type`, `size`, `download_url` 等）。

### 6.3 下载 URL（本地）

- `redirect`：返回应用内短时 token URL，例如  
  `GET .../local/files:download?object_key=...&token=...`（或 signed query，过期时间默认 600s，与 S3 presign 对齐）。
- `proxy`：服务端 `StreamingResponse` 直接返回文件内容。

### 6.4 S3 API（不变路径，修正加载逻辑）

前缀：`/workspaces/{workspace_id}/s3/files` — 行为不变，仅内部配置选取按 §4.4。

### 6.5 错误码（新增/沿用）

| code | HTTP | 场景 |
|------|------|------|
| `file_storage.local_path_invalid` | 422 | local_path 格式非法 |
| `file_storage.type_invalid` | 422 | 启用行 type 非 S3/LOCAL |
| `local.storage_not_active` | 422 | 当前为 S3 启用，调用 local API |
| `local.object_not_found` | 404 | 对象不存在 |
| `local.path_escape` | 422 | 解析路径越界 |

---

## 7. 前端：系统设置 > 文件存储

路径：`/app/settings/file-storage`（`FileStoragePage.tsx`）

### 7.1 表单

- `type=LOCAL`：
  - 显示 `local_path`（可选，placeholder 示例：`backup`）。
  - 隐藏 `bucket_name`、`endpoint_url`、`auth_type` 及凭证字段；提交时 `auth_type=NONE`。
- `type=S3`：保持现有字段与校验。

### 7.2 列表

- 新增列「本地路径」：LOCAL 显示 `local_path` 或 `—`（空表示 workspace 根）。
- `enabled` Switch：调用 patch 后刷新列表以展示互斥结果（其他行应变更为禁用）。

### 7.3 字典

`STORGE_TYPE` 字典需包含 `LOCAL` 项（种子 SQL 或迁移脚本补充；前端已有 `STORGE_TYPE` 字典码）。

### 7.4 i18n

在 `settings.fileStorageLocalPath` 等 key 下补充中英文文案。

---

## 8. 业务模块集成约定

读写文件前：

```python
active = await resolve_active_storage(session, workspace_id)
if active.kind == "S3":
    # S3FileService 或 HTTP /s3/files
elif active.kind in ("LOCAL", "DEFAULT_LOCAL"):
    # LocalFileService 或 HTTP /local/files
```

本期 OCR、Dataset 等**不强制**改造；后续迭代可逐模块切换。

---

## 9. 测试要点

### 9.1 后端

- LOCAL 创建/更新：`local_path` 校验、auth 强制 NONE。
- 互斥：启用 A 后 B.enabled=False；事务一致性。
- `resolve_active_storage`：无启用 → DEFAULT_LOCAL；LOCAL 启用 → 正确 path；S3 启用 → S3。
- `LocalFileService`：上传/列表/下载/删除；路径穿越拒绝。
- 默认兜底：无 sys_storage 或全部 disabled 时 local API 可写读。
- S3 加载：仅 enabled S3 行生效。

### 9.2 前端

- LOCAL 表单字段显隐；列表 local_path 列；Switch 互斥后列表状态。

---

## 10. 实现对照（以代码为准，2026-06-30）

| spec 条目 | 代码位置 | 状态 |
|-----------|----------|------|
| `local_path` 列 | `backend/sql/schema_postgresql.sql`, `patches/2026-06-30-sys-storage-local-path.sql`, `SysStorage` | 已实现 |
| `FILE_STORAGE_LOCAL_ROOT` | `config.py` `resolve_file_storage_local_root()`, `.env.example`, `.env.dev` | 已实现 |
| 路径校验与 root 解析 | `file_storage/service/path_validation.py` | 已实现 |
| `resolve_active_storage` | `file_storage/service/storage_resolver.py` | 已实现 |
| 启用互斥 | `file_storage_service.create/update` + `repository.disable_others_for_workspace` | 已实现 |
| `app/local/*` | `backend/app/local/`（api/domain/infrastructure/service） | 已实现 |
| local files API 挂载 | `local/api/router.py`, `core/api/router.py` | 已实现 |
| S3 加载修正 | `s3_file_service._load_storage_config`（enabled + type=S3） | 已实现 |
| 设置 API `local_path` | `file_storage/api/schemas.py`, `router.py` | 已实现 |
| 设置页 LOCAL UI | `FileStoragePage.tsx`, `fileStorage.ts`, i18n | 已实现 |
| STORGE_TYPE 种子 | `patches/2026-06-30-storge-type-local-dict-item.sql` | 已实现 |
| 业务模块迁移 OCR/Dataset | — | 未做（非目标） |

---

## 11. 方案备选（记录）

| 方案 | 说明 | 结论 |
|------|------|------|
| 1. 平行 `app/local/` | 对齐现有 S3 模块 | **采用** |
| 2. 共享 `app/files/common/` | 抽 key/分页，双路由 | 本期范围偏大 |
| 3. 统一 `/files` 路由 | 内部按类型分发 | 与用户决策不符 |
