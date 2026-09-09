import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * The project keeps ONE .env, at the repository root, shared with the backend.
 * Vite looks in its own folder by default, so point it at that root instead.
 *
 * Walking up from this file (rather than hardcoding '..') means it keeps
 * working whichever folder the frontend ends up in.
 *
 * Only variables prefixed VITE_ are exposed to the browser. DATABASE_URL,
 * JWT_SECRET_KEY and the rest sit in the same file but never reach the bundle.
 */
function findRepoRoot(start) {
  let dir = start
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, '.env'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return start
}

const here = dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  envDir: findRepoRoot(here),
})
