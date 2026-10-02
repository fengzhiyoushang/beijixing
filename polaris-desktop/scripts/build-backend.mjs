/* 用 PyInstaller 打包后端（onedir），产物拷贝到 resources/backend */
import { execSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { delimiter, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')
const REPO = resolve(ROOT, '..')
const BACKEND = join(REPO, 'polaris-backend')
const PY = process.platform === 'win32'
  ? join(BACKEND, '.venv', 'Scripts', 'python.exe')
  : join(BACKEND, '.venv', 'bin', 'python')

console.log('→ PyInstaller 打包后端（onedir）')
execSync(`"${PY}" -m PyInstaller polaris-backend.spec --noconfirm --clean`, {
  cwd: BACKEND,
  stdio: 'inherit',
  env: { ...process.env, PATH: dirname(PY) + delimiter + process.env.PATH },
})

const src = join(BACKEND, 'dist', 'polaris-backend')
const dst = join(ROOT, 'resources', 'backend')
if (!existsSync(src)) {
  console.error('✗ PyInstaller 产物缺失：' + src)
  process.exit(1)
}
rmSync(dst, { recursive: true, force: true })
mkdirSync(dirname(dst), { recursive: true })
cpSync(src, dst, { recursive: true })
console.log('✓ 后端产物 → resources/backend')
