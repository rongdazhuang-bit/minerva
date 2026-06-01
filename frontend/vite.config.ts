import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** FastAPI origin for Vite dev proxy (browser at http://localhost:5173). */
const devApiProxyTarget =
  process.env.MINERVA_DEV_API_PROXY_TARGET ??
  process.env.VITE_DEV_API_PROXY_TARGET ??
  'http://127.0.0.1:8000'

/**
 * 开发代理超时（毫秒）。须大于后端 AI 读超时（默认 120s），否则润色/对话等长请求会得到 ERR_EMPTY_RESPONSE。
 */
const devApiProxyTimeoutMs = Number(
  process.env.MINERVA_DEV_API_PROXY_TIMEOUT_MS ?? 180_000,
)

const devApiProxy = {
  target: devApiProxyTarget,
  changeOrigin: true,
  timeout: devApiProxyTimeoutMs,
  proxyTimeout: devApiProxyTimeoutMs,
}

/** /auth POST 走 API；GET 多为 SPA，但 /auth/login/captcha 与 register/captcha 须代理到后端。 */
const authApiProxy = {
  ...devApiProxy,
  bypass(req) {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      return
    }
    const path = (req.url ?? '').split('?')[0] ?? ''
    if (path.endsWith('/captcha')) {
      return
    }
    return '/index.html'
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '^/auth': authApiProxy,
      '^/(healthz|workspaces|docs|openapi\\.json|redoc)': devApiProxy,
      '^/(ratelimit-probe|validation-probe)': devApiProxy,
    },
  },
})
