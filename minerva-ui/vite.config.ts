/// <reference types="vitest/config" />
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** FastAPI origin for Vite dev proxy (browser at http://localhost:5173). */
const devApiProxyTarget =
  process.env.MINERVA_DEV_API_PROXY_TARGET ??
  process.env.VITE_DEV_API_PROXY_TARGET ??
  'http://127.0.0.1:8000'

const devApiProxy = {
  target: devApiProxyTarget,
  changeOrigin: true,
  /** 避免后端不可达时请求无限挂起。 */
  timeout: 15_000,
  proxyTimeout: 15_000,
}

/** ``/auth`` 下仅有 POST API；GET 为 SPA 路由，须回退到 ``index.html``。 */
const authApiProxy = {
  ...devApiProxy,
  bypass(req) {
    if (req.method === 'GET' || req.method === 'HEAD') {
      return '/index.html'
    }
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
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
