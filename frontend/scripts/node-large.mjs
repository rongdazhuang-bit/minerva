#!/usr/bin/env node
/**
 * Run a Node CLI with a larger V8 heap (build OOM mitigation).
 * Usage: node scripts/node-large.mjs <script.js> [...args]
 * Env: MINERVA_NODE_MAX_OLD_SPACE_SIZE (MB, default 4096)
 */
import { spawnSync } from 'node:child_process'

const heapMb = Number(process.env.MINERVA_NODE_MAX_OLD_SPACE_SIZE ?? 4096)
const [script, ...args] = process.argv.slice(2)

if (!script) {
  console.error('Usage: node scripts/node-large.mjs <script.js> [...args]')
  process.exit(1)
}

if (!Number.isFinite(heapMb) || heapMb < 512) {
  console.error('MINERVA_NODE_MAX_OLD_SPACE_SIZE must be a number >= 512 (MB)')
  process.exit(1)
}

const result = spawnSync(
  process.execPath,
  [`--max-old-space-size=${Math.trunc(heapMb)}`, script, ...args],
  { stdio: 'inherit', env: process.env },
)

process.exit(result.status ?? 1)
