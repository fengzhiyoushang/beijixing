/* 一键打包：构建前端 → PyInstaller 后端 → electron-builder 安装包
 * 内置国内镜像与独立缓存目录（规避 GitHub 超时与 winCodeSign/NSIS 缓存锁问题）。 */
import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')

const env = {
  ...process.env,
  ELECTRON_MIRROR: process.env.ELECTRON_MIRROR || 'https://npmmirror.com/mirrors/electron/',
  ELECTRON_BUILDER_BINARIES_MIRROR:
    process.env.ELECTRON_BUILDER_BINARIES_MIRROR || 'https://npmmirror.com/mirrors/electron-builder-binaries/',
  ELECTRON_BUILDER_CACHE: process.env.ELECTRON_BUILDER_CACHE || resolve(ROOT, '.builder-cache'),
}

function run(cmd, args) {
  // shell:true 下必须给含空格的路径加引号，否则会被截断（如 "F:\deepseek harness ..."）
  const q = (s) => (/\s/.test(s) ? `"${s}"` : s)
  console.log(`\n> ${q(cmd)} ${args.map(q).join(' ')}`)
  const r = spawnSync(cmd, args.map(q), { cwd: ROOT, stdio: 'inherit', env, shell: true })
  if (r.status !== 0) process.exit(r.status ?? 1)
}

run('node', [resolve(HERE, 'build-web.mjs')])
run('node', [resolve(HERE, 'build-backend.mjs')])
run('npx', ['electron-builder', '--win', '--x64'])
console.log('\n✓ 打包完成，产物见 release/ 目录')
