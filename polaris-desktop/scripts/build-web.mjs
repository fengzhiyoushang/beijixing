/* 构建前端并拷贝 dist 到 resources/dist（供 electron-builder extraResources 使用） */
import { execSync } from 'node:child_process'
import { cpSync, mkdirSync, rmSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Electron 二进制与 builder 工具链走国内镜像（GitHub 直连常超时）
process.env.ELECTRON_MIRROR ||= 'https://npmmirror.com/mirrors/electron/'
process.env.ELECTRON_BUILDER_BINARIES_MIRROR ||= 'https://npmmirror.com/mirrors/electron-builder-binaries/'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')
const REPO = resolve(ROOT, '..')

console.log('→ 构建前端 polaris-terminal')
execSync('npm run build', { cwd: join(REPO, 'polaris-terminal'), stdio: 'inherit', shell: true })

const src = join(REPO, 'polaris-terminal', 'dist')
const dst = join(ROOT, 'resources', 'dist')
if (!existsSync(join(src, 'index.html'))) {
  console.error('✗ 前端构建产物缺失：' + src)
  process.exit(1)
}
rmSync(dst, { recursive: true, force: true })
mkdirSync(dirname(dst), { recursive: true })
cpSync(src, dst, { recursive: true })
console.log('✓ dist → resources/dist')
