# S3 文件存储后端接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `backend/app/s3` 交付可复用的 S3 文件对象能力，基于 `sys_storage` 配置提供上传、列表、下载、删除四个服务端接口。

**Architecture:** 新增 `app/s3` 垂直切片模块（`api/service/infrastructure/domain`），由 service 层统一校验 workspace 与 `sys_storage` 配置，再委托 gateway 调用 S3 SDK。列表对外维持 `page/page_size` 语义；下载默认返回预签名 URL 的 302，支持 `proxy` 流式回传。错误统一收敛为 `AppError`。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, boto3(botocore), pytest + httpx.

**设计依据:** `docs/superpowers/specs/2026-04-30-s3-file-storage-design.md`

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/pyproject.toml` | 增加 S3 SDK 依赖（`boto3`） |
| `backend/app/s3/__init__.py` | 模块导出说明 |
| `backend/app/s3/domain/__init__.py` | 域子包导出 |
| `backend/app/s3/domain/models.py` | 文件项、分页、下载模式等领域模型 |
| `backend/app/s3/infrastructure/__init__.py` | 基础设施子包导出 |
| `backend/app/s3/infrastructure/client_factory.py` | 从 `SysStorage` 构建 S3 client 与 bucket 信息 |
| `backend/app/s3/infrastructure/s3_gateway.py` | 封装 put/list/get/delete/presign 与异常映射 |
| `backend/app/s3/service/__init__.py` | 服务子包导出 |
| `backend/app/s3/service/s3_file_service.py` | 业务编排、key 生成、参数/权限相关校验 |
| `backend/app/s3/api/__init__.py` | API 子包导出 |
| `backend/app/s3/api/schemas.py` | 请求/响应模型（含分页） |
| `backend/app/s3/api/router.py` | 4 个接口路由与依赖注入 |
| `backend/app/api/router.py` | 挂载 S3 router |
| `backend/tests/test_s3_file_api.py` | API 集成测试（mock 掉 S3 gateway） |

---

## Task 1: 依赖与模块脚手架

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/s3/__init__.py`
- Create: `backend/app/s3/domain/__init__.py`
- Create: `backend/app/s3/infrastructure/__init__.py`
- Create: `backend/app/s3/service/__init__.py`
- Create: `backend/app/s3/api/__init__.py`

- [ ] **Step 1: 先写失败导入测试（最小）**

创建 `backend/tests/test_s3_file_api.py` 最小 smoke case（先失败）：

```python
def test_import_s3_router_module() -> None:
    from app.s3.api import router  # noqa: F401
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_import_s3_router_module -v
```

Expected: FAIL（`ModuleNotFoundError: No module named 'app.s3'`）。

- [ ] **Step 3: 增加依赖与空包**

`pyproject.toml` 增加依赖：

```toml
dependencies = [
  # ... existing
  "boto3>=1.35",
]
```

各 `__init__.py` 至少包含模块 docstring：

```python
"""S3 file storage module package."""
```

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_import_s3_router_module -v
```

Expected: 仍 FAIL（此时会因 `router.py` 尚不存在而失败，符合预期）。

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/s3/__init__.py backend/app/s3/domain/__init__.py backend/app/s3/infrastructure/__init__.py backend/app/s3/service/__init__.py backend/app/s3/api/__init__.py backend/tests/test_s3_file_api.py
git commit -m "chore(s3): add dependency and module skeleton"
```

---

## Task 2: Domain 与 Schema（先测试后实现）

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`
- Create: `backend/app/s3/domain/models.py`
- Create: `backend/app/s3/api/schemas.py`

- [ ] **Step 1: 编写失败测试（模型契约）**

在 `test_s3_file_api.py` 新增：

```python
def test_s3_list_page_schema_defaults() -> None:
    from app.s3.api.schemas import S3FileListPageOut

    page = S3FileListPageOut(items=[], total=0, page=1, page_size=10)
    assert page.total == 0
    assert page.page_size == 10
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_s3_list_page_schema_defaults -v
```

Expected: FAIL（`cannot import name` 或模型不存在）。

- [ ] **Step 3: 实现领域模型与 API schema**

`domain/models.py` 定义：

```python
class S3ObjectItem(BaseModel):
    object_key: str
    filename: str
    size: int
    etag: str | None = None
    last_modified: datetime | None = None
```

`api/schemas.py` 定义：

```python
class S3FileListPageOut(BaseModel):
    items: list[S3ObjectItem] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100, default=10)
```

另补齐上传/删除/下载所需入参与出参模型（含 `storage_id`、`module_prefix`、`object_key`、`mode`）。

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_s3_list_page_schema_defaults -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/s3/domain/models.py backend/app/s3/api/schemas.py backend/tests/test_s3_file_api.py
git commit -m "feat(s3): add domain and schema models"
```

---

## Task 3: 基础设施 client_factory（sys_storage -> S3 配置）

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`
- Create: `backend/app/s3/infrastructure/client_factory.py`

- [ ] **Step 1: 写失败测试（认证映射与配置校验）**

新增测试（可用 `pytest.mark.asyncio`）：

```python
async def test_build_s3_client_rejects_disabled_storage() -> None:
    from app.s3.infrastructure.client_factory import build_client_context
    from app.exceptions import AppError
    with pytest.raises(AppError) as exc:
        await build_client_context(session, workspace_id=wid, storage_id=sid)  # 准备 enabled=false 夹具
    assert exc.value.code == "s3.storage_not_enabled"
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_build_s3_client_rejects_disabled_storage -v
```

Expected: FAIL（函数不存在）。

- [ ] **Step 3: 实现 `build_client_context`**

在 `client_factory.py` 中：
- 查询 `SysStorage`（workspace 范围）
- 校验 `enabled` 与 `type == "S3"`（大小写归一）
- 解析 endpoint 与 bucket（约定：`endpoint_url` 存储 `https://host/bucket` 或 `https://host` + `name` 为 bucket，按实现选其一并在注释中固定）
- 认证：
  - `API_KEY`：从 `api_key` 解析 `access_key:secret_key`
  - `BASIC`：`auth_name/auth_passwd`
- 创建 boto3 client（`boto3.client("s3", ...)`）并返回上下文对象

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_build_s3_client_rejects_disabled_storage -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/s3/infrastructure/client_factory.py backend/tests/test_s3_file_api.py
git commit -m "feat(s3): build s3 client context from sys_storage"
```

---

## Task 4: 基础设施 gateway（S3 操作与异常映射）

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`
- Create: `backend/app/s3/infrastructure/s3_gateway.py`

- [ ] **Step 1: 写失败测试（异常映射）**

新增测试：

```python
def test_map_not_found_error_to_app_error() -> None:
    from app.s3.infrastructure.s3_gateway import map_s3_error
    err = map_s3_error("NoSuchKey", "missing")
    assert err.code == "s3.object_not_found"
    assert err.status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_map_not_found_error_to_app_error -v
```

Expected: FAIL（函数不存在）。

- [ ] **Step 3: 实现 gateway 操作函数**

实现（函数名可微调，但对外契约一致）：
- `upload_object(...)`
- `list_objects_page(...)`
- `generate_download_url(...)`
- `download_object_stream(...)`
- `delete_object(...)`
- `map_s3_error(...)`

异常映射最少覆盖：`NoSuchKey`、`AccessDenied`、`NoSuchBucket`、默认兜底 `s3.request_failed`。

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_map_not_found_error_to_app_error -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/s3/infrastructure/s3_gateway.py backend/tests/test_s3_file_api.py
git commit -m "feat(s3): add s3 gateway operations and error mapping"
```

---

## Task 5: Service 编排（key 规则、分页封装、校验）

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`
- Create: `backend/app/s3/service/s3_file_service.py`

- [ ] **Step 1: 写失败测试（key 生成规则）**

新增测试：

```python
def test_build_object_key_with_module_prefix() -> None:
    from app.s3.service.s3_file_service import build_object_key
    key = build_object_key(module_prefix="ocr", filename="a.pdf", now=datetime(2026, 4, 30, tzinfo=UTC), object_id=UUID("11111111-1111-1111-1111-111111111111"))
    assert key == "ocr/2026/04/11111111-1111-1111-1111-111111111111.pdf"
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_build_object_key_with_module_prefix -v
```

Expected: FAIL。

- [ ] **Step 3: 实现 service**

实现核心函数：
- `validate_module_prefix(...)`
- `validate_object_key(...)`
- `build_object_key(...)`
- `upload_file(...)`
- `list_files(...)`
- `get_download_redirect(...)`
- `iter_download_proxy(...)`
- `delete_file(...)`

要点：
- 默认 `page_size` 使用 `app.pagination.DEFAULT_PAGE_SIZE`
- 分页对外 `page/page_size`
- 下载默认 redirect，兼容 proxy

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_build_object_key_with_module_prefix -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/s3/service/s3_file_service.py backend/tests/test_s3_file_api.py
git commit -m "feat(s3): add service orchestration and key strategy"
```

---

## Task 6: API 路由实现并注册

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`
- Create: `backend/app/s3/api/router.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: 写失败 API 测试（先红）**

新增端点测试（可通过 monkeypatch service 方法，避免真实 S3）：

```python
@pytest.mark.asyncio
async def test_s3_list_endpoint_returns_page() -> None:
    # register -> token -> wid
    # monkeypatch svc.list_files 返回固定 page 对象
    r = await ac.get(f"/workspaces/{wid}/s3/files?storage_id={sid}&page=1&page_size=10", headers=h)
    assert r.status_code == 200
    assert "items" in r.json()
```

- [ ] **Step 2: 运行确认失败**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_s3_list_endpoint_returns_page -v
```

Expected: FAIL（404，路由未注册）。

- [ ] **Step 3: 实现 4 个路由并挂载**

在 `router.py` 实现：
- `POST /workspaces/{workspace_id}/s3/files:upload`
- `GET /workspaces/{workspace_id}/s3/files`
- `GET /workspaces/{workspace_id}/s3/files:download`
- `DELETE /workspaces/{workspace_id}/s3/files`

并在 `app/api/router.py` 添加：

```python
from app.s3.api.router import router as s3_router
api.include_router(s3_router)
```

- [ ] **Step 4: 重跑测试**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py::test_s3_list_endpoint_returns_page -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/s3/api/router.py backend/app/api/router.py backend/tests/test_s3_file_api.py
git commit -m "feat(s3): add and register file operation APIs"
```

---

## Task 7: 端到端用例测试（上传/列表/下载/删除 + 权限）

**Files:**
- Modify: `backend/tests/test_s3_file_api.py`

- [ ] **Step 1: 编写主链路测试（先失败）**

新增测试集合：
- `test_s3_file_crud_flow_with_mock_gateway`
- `test_s3_forbidden_for_non_member`
- `test_s3_download_redirect_and_proxy_mode`

用法：
- 使用 `auth/register` 获取两个用户及 token
- 创建/准备 `sys_storage` 数据（可通过现有 file_storage API 创建）
- monkeypatch gateway 返回可预测结果
- 断言状态码、返回字段、权限隔离

- [ ] **Step 2: 运行并观察失败原因**

Run:

```bash
cd backend && pytest tests/test_s3_file_api.py -v
```

Expected（实现前半阶段）: 至少一条 FAIL。

- [ ] **Step 3: 修补实现到全绿**

根据失败信息修补 service/router/gateway 的边界行为：
- 空文件
- 非法 `module_prefix`
- 非法 `object_key`
- `mode` 非法值
- 错误码一致性

- [ ] **Step 4: 全量后端测试回归**

Run:

```bash
cd backend && pytest -q
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_s3_file_api.py backend/app/s3
git commit -m "test(s3): cover s3 file API flow and access control"
```

---

## Task 8: 注释规范与代码整理收尾

**Files:**
- Modify: `backend/app/s3/**/*.py`（本模块全部）

- [ ] **Step 1: 注释自检**

按仓库规则检查：
- 每个 `.py` 有模块 docstring
- 每个 class / def（含私有函数）有 docstring
- 模块常量与语义不直观变量有说明

- [ ] **Step 2: 质量检查**

Run:

```bash
cd backend && python -m compileall app/s3
cd backend && pytest tests/test_s3_file_api.py -v
```

Expected: 编译通过 + 新增测试 PASS。

- [ ] **Step 3: 最终提交**

```bash
git add backend/app/s3 backend/app/api/router.py backend/pyproject.toml backend/tests/test_s3_file_api.py
git commit -m "feat(s3): implement workspace s3 file operations backend"
```

---

## Spec 对照自检（计划作者填写）

| 规格要求 | 对应任务 |
|----------|----------|
| `app/s3` 新模块与分层边界 | Task 1–2 |
| 配置来源 `sys_storage` + S3 类型/启用校验 | Task 3 |
| 认证支持 `API_KEY` + `BASIC` | Task 3 |
| 上传/列表/下载/删除四接口 | Task 6 |
| key 规则 `module_prefix/YYYY/MM/uuid.ext` | Task 5 |
| 列表分页 `page/page_size` 默认 10 | Task 5 + Task 6 |
| 下载 `redirect` 默认 + `proxy` 兼容 | Task 5 + Task 6 + Task 7 |
| 错误码映射与权限隔离 | Task 4 + Task 7 |
| 测试覆盖主链路与异常场景 | Task 7 |

**Placeholder 扫描:** 本计划无 TBD/TODO；每个任务含具体文件、命令、断言与提交建议。  
**类型一致性:** schema/service/router 中统一使用 `storage_id/module_prefix/object_key/page/page_size` 命名。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-04-30-s3-file-storage.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks in this session using checkpoints. **REQUIRED SUB-SKILL:** `superpowers:executing-plans`.

Which approach would you like to use?
