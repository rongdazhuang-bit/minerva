# API 接口 `/api` 根前缀设计说明

**日期**：2026-06-23  
**状态**：已实现（2026-06-23）  
**范围**：为所有业务 API 统一添加 `/api` 根前缀；前后端路径对齐；开发代理与 Nginx 转发约定。  
**不包含**：生产 Nginx 具体配置落地、历史 spec/plan 文档批量修订。

---

## 1. 目标与成功标准

### 1.1 产品决策（已确认）

| 项 | 决策 |
|---|---|
| 前缀范围 | **仅业务 API**（`/auth`、`/sys`、`/workspaces` 等）→ `/api/...` |
| 根路径保留 | `/healthz`、`/docs`、`/openapi.json`、`/redoc`、`/mcp/s/{slug}` 保持根路径 |
| 测试探针 | `/ratelimit-probe`、`/validation-probe` 保持根路径（从业务聚合路由拆出） |
| 兼容策略 | **硬切换**：旧路径（如 `/auth/login`）直接 404，无重定向、无双挂载 |
| 部署 | 前端配置 API 前缀；经 Nginx 将 `/api/*` 转发至后端（保留 `/api` 前缀） |
| 实现策略 | **集中挂载**：后端 `main.py` 一处 `prefix="/api"`；前端 `config.ts` 一处 `API_PATH_PREFIX` |

### 1.2 成功标准

- 所有业务 API 可通过 `/api/...` 访问；`/healthz`、`/docs`、MCP 出站路径行为与变更前一致。
- 前端 `api/*.ts` 路径字面量无需逐文件修改；`apiJson` / `authFetch` / `apiOrigin()` 自动拼接前缀。
- 开发环境 Vite 代理简化：`^/api` 统一转发，SPA `/auth/login` 与 API 不再路径冲突。
- 旧业务路径（无 `/api`）返回 404。

---

## 2. 路径归属表

| 变更前 | 变更后 | 挂载位置 |
|--------|--------|----------|
| `/auth/*` | `/api/auth/*` | `app.include_router(api, prefix="/api")` |
| `/sys/*` | `/api/sys/*` | 同上 |
| `/workspaces/{id}/*` | `/api/workspaces/{id}/*` | 同上 |
| `/healthz` | `/healthz` | `app.include_router(health.router)` |
| `/ratelimit-probe`、`/validation-probe` | 不变 | `app.include_router(probe.router)` |
| `/docs`、`/openapi.json`、`/redoc` | 不变 | FastAPI 默认 |
| `/mcp/s/{slug}` | 不变 | `mount_mcp_server_routes(app)` |

---

## 3. 后端设计

### 3.1 路由挂载（`backend/app/main.py`）

```python
from app.core.api.routers import health, probe
from app.core.api.router import api

app.include_router(health.router)
app.include_router(probe.router)
app.include_router(api, prefix="/api")
# mount_mcp_server_routes(app) 生命周期内逻辑不变
```

### 3.2 聚合路由（`backend/app/core/api/router.py`）

- **移除** `health.router`、`probe.router` 的 `include_router`。
- 其余模块（`auth`、`sys/*`、`workspaces/*`、`agent`、`dataset` 等）保持各模块内部 `prefix` 不变。

### 3.3 模块内 prefix

各业务 router 现有 prefix（如 `/auth`、`/workspaces/{workspace_id}/users`）**不修改**；全局 `/api` 由 `main.py` 统一追加。

### 3.4 OpenAPI

FastAPI 自动在 schema 中展示 `/api/*` 路径；文档入口仍为 `http://host/docs`。

---

## 4. 前端设计

### 4.1 配置（`frontend/src/api/config.ts`）

```ts
/** 业务 API 路径前缀；可与 VITE_API_PATH_PREFIX 对齐（默认同源 /api）。 */
export const API_PATH_PREFIX =
  (import.meta.env.VITE_API_PATH_PREFIX ?? '/api').replace(/\/$/, '') || '/api'

export function resolveApiBaseUrl(): string {
  // 现有逻辑：VITE_API_BASE_URL 或空字符串（同源）
}

/** API 根地址：host + /api，无尾部斜杠。 */
export function apiOrigin(): string {
  return `${resolveApiBaseUrl()}${API_PATH_PREFIX}`
}
```

- `VITE_API_BASE_URL`：主机部分（如 `https://api.example.com` 或空表示同源）。
- `VITE_API_PATH_PREFIX`：可选覆盖，默认 `/api`。

### 4.2 HTTP 客户端（`frontend/src/api/client.ts`）

- `publicApiJson`、`apiJson` 使用 `apiOrigin()` 替代裸 `resolveApiBaseUrl()` 拼接。
- 各 `api/*.ts` 中路径参数保持 `/auth/login`、`/workspaces/...` 形式，**不重复写 `/api`**。

### 4.3 认证路径判断（`frontend/src/api/tokenSession.ts`）

请求 URL 将变为 `/api/auth/*`，需更新：

| 函数 | 变更后逻辑 |
|------|------------|
| `isAuthApiPath` | `pathname.startsWith('/api/auth/')` |
| `isAuthCaptchaApiPath` | `/api/auth/login/captcha`、`/api/auth/register/captcha` |

`isOnAuthUi` 仍判断 SPA 路由 `/auth/login` 等，**不变**。

### 4.4 直连 fetch 的文件

以下文件通过 `apiOrigin()` 拼接完整 URL，随 `apiOrigin()` 变更自动生效，无需改路径字面量：

- `api/agent.ts`、`api/agentSkillsMgmt.ts`、`api/translate.ts`、`api/ocrTask.ts`
- `features/dataset/api/datasets.ts`

### 4.5 环境变量示例（`frontend/.env.example`）

```env
# VITE_API_BASE_URL=
# VITE_API_PATH_PREFIX=/api
```

---

## 5. 开发环境 Vite 代理

**变更前**：`^/auth` 需 bypass 区分 SPA 与 API。  
**变更后**：API 与 SPA 路径分离，代理规则简化：

```ts
proxy: {
  '^/api': devApiProxy,
  '^/(healthz|docs|openapi\\.json|redoc)': devApiProxy,
  '^/(ratelimit-probe|validation-probe)': devApiProxy,
  '^/mcp': devApiProxy,
}
```

删除 `authApiProxy` 及其 `bypass` 逻辑。

---

## 6. Nginx 参考

见仓库 **`scripts/nginx/minerva.conf`**（同源托管前端 + `/api/*` 转发后端）。

---

## 7. 测试与文档

| 项 | 处理 |
|----|------|
| 后端测试 | 若有硬编码业务路径，改为 `/api/...` |
| README | 更新 API 示例 URL（业务 API 加 `/api`；`/healthz`、`/docs` 示例不变） |
| 历史 spec/plan | 不批量修改 |

---

## 8. 改动文件清单

| 区域 | 文件 | 改动 |
|------|------|------|
| 后端 | `app/main.py` | 拆分 health/probe 挂载；`api` 加 `prefix="/api"` |
| 后端 | `app/core/api/router.py` | 移除 health、probe |
| 前端 | `src/api/config.ts` | `API_PATH_PREFIX`、`apiOrigin()` |
| 前端 | `src/api/client.ts` | 使用 `apiOrigin()` 拼接 |
| 前端 | `src/api/tokenSession.ts` | `/api/auth/*` 路径判断 |
| 前端 | `vite.config.ts` | 代理规则简化 |
| 前端 | `.env.example` | 可选 `VITE_API_PATH_PREFIX` 注释 |
| 文档 | `README.md`、`README.en.md` | API URL 示例 |

**无需修改**：`frontend/src/api/*.ts` 业务路径字面量、各后端模块 router 内部 prefix、MCP server 挂载逻辑。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 外部脚本/集成仍调用旧路径 | 硬切换前通知调用方；README 更新 |
| `isAuthApiPath` 未更新导致 refresh 逻辑异常 | 实现时覆盖 tokenSession 单测或手动验证登录/refresh |
| Nginx 误 strip `/api` | 文档明确 `proxy_pass` 保留前缀 |

---

## 10. 未采纳方案

- **分散改各 router prefix**：改动面大、易遗漏。
- **仅 Nginx 加前缀、后端不变**：前后端路径不一致，不符合需求。
- **旧路径重定向 / 双挂载**：增加维护成本，已明确硬切换。
