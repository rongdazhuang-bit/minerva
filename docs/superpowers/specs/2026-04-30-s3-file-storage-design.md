# S3 文件存储能力（全局配置 + 通用后端接口）设计说明

**日期**：2026-04-30  
**状态**：已评审待实现  
**范围**：在 `backend/app/s3/` 实现可复用的 S3 文件对象能力，配置来源于 `sys_storage`（全局 S3 配置），支持 `API_KEY` 与 `BASIC` 认证，提供服务端接口：上传、列表、下载、删除，供多个业务模块复用。

---

## 1. 目标与成功标准

### 1.1 目标

- 在不改变现有 `sys_storage` 配置管理职责的前提下，新增 `app/s3` 负责对象操作能力。
- 通过 `storage_id` 从 `sys_storage` 加载 S3 连接与认证配置，构建 SDK 客户端并执行文件对象操作。
- 提供统一后端 API：上传（create）、列表（read/list）、下载（read/get）、删除（delete）。
- 对多个模块提供可复用服务层，不要求每个业务模块重复实现 S3 调用细节。
- 对外统一错误语义并映射到项目既有 `AppError` 体系。

### 1.2 成功标准

- 可在指定 workspace 下，使用一个启用中的 `sys_storage`（S3 类型）完成上传、列表、下载、删除全链路。
- 列表接口对调用方暴露 `page/page_size` 分页语义，默认每页 10 条。
- 对象 key 统一遵循 `module_prefix/YYYY/MM/<uuid>.<ext>`。
- 配置无效、认证失败、对象不存在、网络失败等典型错误均返回稳定错误码。

### 1.3 非目标（本期）

- 不引入前端页面与交互实现（仅服务端接口）。
- 不做多云抽象（OSS/COS/OBS 等），仅实现 S3 能力。
- 不实现跨 workspace 共享与对象级复杂 ACL 管理。

---

## 2. 架构与目录结构

### 2.1 模块职责

- `app/sys/file_storage`：管理 `sys_storage` 配置（已有 CRUD，继续保留）。
- `app/s3`：管理运行时对象操作（上传、列表、下载、删除）和 S3 SDK 适配。

### 2.2 建议目录

```text
backend/app/s3/
  __init__.py
  api/
    __init__.py
    router.py            # FastAPI 路由
    schemas.py           # 请求/响应模型
  domain/
    __init__.py
    models.py            # 对象元数据、分页结果等领域模型
  infrastructure/
    __init__.py
    client_factory.py    # 读取 sys_storage 后创建 S3 client
    s3_gateway.py        # 封装 put/list/get/delete 与异常映射
  service/
    __init__.py
    s3_file_service.py   # 业务编排、参数校验、key 生成
```

### 2.3 与现有系统集成

- 在 `backend/app/api/router.py` 中挂载 `app/s3/api/router.py`。
- 数据源沿用现有 `sys_storage` 表，不新增配置表。
- 认证与 workspace 权限依赖复用现有 `app.api.deps`。

---

## 3. 接口设计

### 3.1 上传

- `POST /workspaces/{workspace_id}/s3/files:upload`
- `multipart/form-data` 字段：
  - `storage_id`（必填）
  - `module_prefix`（必填）
  - `file`（必填）
  - `filename`（可选，默认取上传文件名）
- 响应字段（建议）：
  - `object_key`
  - `bucket`
  - `size`
  - `content_type`
  - `etag`
  - `last_modified`

### 3.2 列表

- `GET /workspaces/{workspace_id}/s3/files`
- Query：
  - `storage_id`（必填）
  - `module_prefix`（可选，不传则按桶范围或业务默认前缀）
  - `page`（默认 1）
  - `page_size`（默认 10，最大 100）
- 响应字段（建议）：
  - `items`：`object_key`、`filename`、`size`、`etag`、`last_modified`
  - `total`
  - `page`
  - `page_size`

> 注：S3 原生以游标分页为主，本模块在服务端封装游标细节，对外维持 `page/page_size` 语义。

### 3.3 下载

- `GET /workspaces/{workspace_id}/s3/files:download`
- Query：
  - `storage_id`（必填）
  - `object_key`（必填）
  - `mode`（可选：`redirect`/`proxy`，默认 `redirect`）
- 返回方式：
  - 默认 `redirect`：返回 302 到短时预签名 URL
  - `proxy`：由服务端流式返回文件内容（内网限制场景备用）

### 3.4 删除

- `DELETE /workspaces/{workspace_id}/s3/files`
- Body：
  - `storage_id`（必填）
  - `object_key`（必填）
- 响应：
  - `204 No Content`

---

## 4. 关键规则与数据约束

### 4.1 配置有效性

- `storage_id` 必须存在且属于当前 workspace。
- `sys_storage.enabled` 必须为 `true`。
- `sys_storage.type` 必须是 `S3`（大小写归一化后比对）。

### 4.2 认证映射

- `API_KEY`：使用 `api_key` 解析出 S3 SDK 所需凭证对（实现期明确字段规则）。
- `BASIC`：使用 `auth_name` + `auth_passwd` 作为凭证来源映射至 SDK。
- 任一认证方式字段不完整时返回 422 业务错误。

### 4.3 对象 key 规则

- 统一格式：`module_prefix/YYYY/MM/<uuid>.<ext>`。
- `module_prefix`：允许 `[a-z0-9][a-z0-9-_]{1,31}`。
- `object_key`：拒绝 `..`、反斜杠、控制字符，长度上限 1024。

### 4.4 权限规则

- 列表/下载：`workspace_member`。
- 上传/删除：`workspace_owner_or_admin`。

---

## 5. 数据流

### 5.1 上传流

```text
API -> 参数与权限校验 -> 加载 sys_storage -> 创建 S3 client
    -> 生成 object_key -> put_object -> 返回元数据
```

### 5.2 列表流

```text
API -> 参数与权限校验 -> 加载 sys_storage -> list_objects_v2
    -> 服务端分页封装(page/page_size) -> 返回列表页
```

### 5.3 下载流

```text
API -> 参数与权限校验 -> 加载 sys_storage -> 检查对象(可选 head)
    -> 生成预签名URL(redirect) 或代理流式输出(proxy)
```

### 5.4 删除流

```text
API -> 参数与权限校验 -> 加载 sys_storage -> delete_object -> 204
```

---

## 6. 错误处理与观测

### 6.1 业务错误码建议

- `s3.storage_not_found`（404）
- `s3.storage_not_enabled`（422）
- `s3.storage_type_invalid`（422）
- `s3.auth_invalid`（422）
- `s3.module_prefix_invalid`（422）
- `s3.object_key_invalid`（422）
- `s3.file_required`（422）
- `s3.object_not_found`（404）
- `s3.access_denied`（403）
- `s3.bucket_not_found`（404）
- `s3.endpoint_unreachable`（502）
- `s3.request_failed`（502，兜底）

### 6.2 异常映射策略

- 将 SDK 异常映射为统一 `AppError(code, message, status)`。
- 不泄露密钥、签名串、完整 endpoint 凭证参数。
- 对网络瞬断和可重试错误可配置有限重试（如 2 次指数退避）。

### 6.3 日志字段

- 建议记录：`workspace_id`、`storage_id`、`module_prefix`、`object_key`、耗时、错误码。
- 禁止记录：`api_key`、`auth_passwd`、完整签名 URL。

---

## 7. 测试设计

### 7.1 单元测试

- key 生成规则与路径合法性校验。
- 认证字段解析与映射（`API_KEY`、`BASIC`）。
- SDK 典型错误到 `AppError` 的映射。
- 分页参数边界（默认值、最大值、非法值）。

### 7.2 集成测试

- 使用 mock S3（或测试 MinIO）验证上传/列表/下载/删除主链路。
- 覆盖 workspace 权限隔离。
- 覆盖配置异常（禁用、类型不符、凭证缺失）。

### 7.3 API 契约测试

- 校验请求参数约束与响应字段稳定性。
- 校验默认分页 10 条行为。
- 校验下载 `redirect/proxy` 两模式的状态码与响应头。

---

## 8. 实施边界与演进

- 本期只交付 S3 后端能力，不绑定任何单一业务模块页面。
- 未来如需扩展多云，优先在 `infrastructure` 层引入 provider 抽象，不破坏 `service/api` 接口。

---

## 9. 规格自检（2026-04-30）

| 项 | 结论 |
|----|------|
| 占位符 / TBD | 无未决 TODO/TBD；认证映射的字段格式已明确在实现阶段细化，但不影响本期边界。 |
| 一致性 | 模块职责（配置管理 vs 对象操作）与接口范围一致，权限与分页规则统一。 |
| 范围 | 聚焦单模块后端能力，规模适合一份实现计划，不含前端与多云扩展。 |
| 歧义 | 下载返回方式明确默认 `redirect`，并保留 `proxy` 兼容模式。 |

---

## 10. 后续工作入口

设计评审通过后，下一步仅进入 **`writing-plans`**，输出实现计划（目录脚手架、路由/服务/网关、测试、文档与验证步骤），不在本设计说明中直接写实现代码。
