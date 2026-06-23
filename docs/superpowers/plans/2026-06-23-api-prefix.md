# API `/api` 根前缀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为所有业务 API 统一 `/api` 前缀，前后端路径对齐，并提供 Nginx 生产配置示例。

**Architecture:** 后端 `main.py` 集中 `prefix="/api"`；health/probe 挂根路径。前端 `API_PATH_PREFIX` + `apiOrigin()` 单点拼接；Vite 代理简化为 `^/api`。

**Tech Stack:** FastAPI, React/Vite, Nginx

**Spec:** [2026-06-23-api-prefix-design.md](../specs/2026-06-23-api-prefix-design.md)

---

### Task 1: 后端路由挂载

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/api/router.py`

- [x] **Step 1:** `main.py` 引入 `health`、`probe`，分别 `include_router` 后 `api` 加 `prefix="/api"`
- [x] **Step 2:** `router.py` 移除 health、probe
- [x] **Step 3:** 验证 `uvicorn` 启动后 `/healthz` 与 `/api/auth/login` 可访问

### Task 2: 前端 API 前缀

**Files:**
- Modify: `frontend/src/api/config.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/tokenSession.ts`
- Modify: `frontend/src/vite-env.d.ts`
- Modify: `frontend/.env.example`

- [x] **Step 1:** 添加 `API_PATH_PREFIX`、`apiOrigin()` 含前缀
- [x] **Step 2:** `client.ts` 使用 `apiOrigin()` 拼接
- [x] **Step 3:** `tokenSession.ts` 更新 `isAuthApiPath` / `isAuthCaptchaApiPath`

### Task 3: 开发代理

**Files:**
- Modify: `frontend/vite.config.ts`

- [x] **Step 1:** 删除 `authApiProxy` bypass 逻辑
- [x] **Step 2:** 代理规则改为 `^/api`、`^/healthz`、`^/mcp` 等

### Task 4: Nginx 与文档

**Files:**
- Create: `scripts/nginx/minerva.conf`
- Modify: `README.md`, `README.en.md`
- Modify: `docs/superpowers/specs/2026-06-23-api-prefix-design.md`（状态已实现）

- [x] **Step 1:** 添加 Nginx 示例（静态前端 + `/api/` 转发）
- [x] **Step 2:** README 更新 API URL 与部署说明

### Task 5: 手动验证

- [ ] **Step 1:** `npm run dev` + `run-backend`，登录/注册正常
- [ ] **Step 2:** `curl http://127.0.0.1:8000/healthz` → 200
- [ ] **Step 3:** `curl http://127.0.0.1:8000/auth/login` → 404；`/api/auth/login` 存在（405/422 亦可）
