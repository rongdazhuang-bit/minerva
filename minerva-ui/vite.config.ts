/// <reference types="vitest/config" />
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** FastAPI origin for Vite dev proxy (host machine only; LAN clients hit Vite on :5173). */
const devApiProxyTarget =
  process.env.MINERVA_DEV_API_PROXY_TARGET ??
  process.env.VITE_DEV_API_PROXY_TARGET ??
  'http://127.0.0.1:8000'

const devApiProxy = {
  target: devApiProxyTarget,
  changeOrigin: true,
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '^/(auth|healthz|workspaces|docs|openapi\\.json|redoc)': devApiProxy,
      '^/(ratelimit-probe|validation-probe)': devApiProxy,
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
