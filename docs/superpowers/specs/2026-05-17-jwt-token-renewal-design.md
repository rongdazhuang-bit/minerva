# JWT Access Token 静默续期设计

**日期**：2026-05-17  
**状态**：已批准实现  
**范围**：前端集中式 token 续期 + 后端 access TTL 默认 60 分钟。

---

## 1. 问题

- `access_token` 默认 15 分钟过期，前端未调用 `POST /auth/refresh`。
- `apiJson` / `agent.ts` 在 401 时直接清 token 并跳转 `/login`。
- 用户持续操作超过约 15 分钟会被踢回登录页。

## 2. 方案（方案 1）

- 新增 `tokenSession`：到期前 2 分钟主动 refresh、401 单飞 refresh 并重试一次。
- `apiJson` / `authFetch` 统一经 token 层；`agent.ts`、`ocrTask` XHR 接入。
- `AuthContext` 订阅 token 更新、调度主动刷新、多标签 `storage` 同步。
- 后端 `jwt_access_ttl_minutes` 默认 **60**（可环境变量覆盖）。

## 3. 非目标

- SSE 流进行中的 mid-stream 续期（场景 C）。
- HttpOnly Cookie 改造。
- 修改 refresh 轮换服务端逻辑。

## 4. 成功标准

- 登录后连续操作 > 20 分钟不跳登录。
- refresh 失效时行为与现有一致（清 token、非认证页跳转登录）。
