/*
 * 后端进程管理：spawn / 就绪检测 / 优雅终止（防孤儿进程）。
 * - 开发态：polaris-backend/.venv 的 python 直接运行 run_backend.py
 * - 生产态：PyInstaller onedir 产物 resources/backend/polaris-backend(.exe)
 * - 数据目录（SQLite / uploads / backups）通过环境变量注入 Electron userData，
 *   config.py 对绝对路径直接采用，绕开冻结后不可写的 BASE_DIR。
 */
const { spawn, spawnSync } = require('node:child_process')
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/** 读取/生成持久化 JWT 密钥（跨重启稳定，避免每次启动都要重新登录） */
function getOrCreateJwtSecret(userData) {
  const file = path.join(userData, 'jwt.secret')
  if (fs.existsSync(file)) {
    const s = fs.readFileSync(file, 'utf-8').trim()
    if (s) return s
  }
  const s = crypto.randomBytes(32).toString('hex')
  fs.mkdirSync(userData, { recursive: true })
  fs.writeFileSync(file, s, 'utf-8')
  return s
}

/**
 * 启动后端子进程。
 * @param {{ backendPort: number, frontPort: number, userData: string,
 *           repoRoot: string, isPackaged: boolean, resourcesPath: string,
 *           logger?: (line: string) => void }} opts
 * @returns {{ child: import('node:child_process').ChildProcess,
 *             waitReady(): Promise<void>, kill(): void }}
 */
function startBackend(opts) {
  const { backendPort, frontPort, userData, repoRoot, isPackaged, resourcesPath } = opts
  const log = opts.logger || (() => {})

  fs.mkdirSync(path.join(userData, 'data'), { recursive: true })
  fs.mkdirSync(path.join(userData, 'uploads'), { recursive: true })
  fs.mkdirSync(path.join(userData, 'backups'), { recursive: true })

  const backendSrc = path.join(repoRoot, 'polaris-backend')
  let exe, args, cwd
  if (isPackaged) {
    const binName = process.platform === 'win32' ? 'polaris-backend.exe' : 'polaris-backend'
    exe = path.join(resourcesPath, 'backend', binName)
    args = []
    cwd = userData
  } else {
    exe = process.platform === 'win32'
      ? path.join(backendSrc, '.venv', 'Scripts', 'python.exe')
      : path.join(backendSrc, '.venv', 'bin', 'python')
    args = [path.join(backendSrc, 'run_backend.py')]
    cwd = backendSrc
  }

  const env = {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(backendPort),
    DB_BACKEND: 'sqlite',
    SQLITE_PATH: path.join(userData, 'data', 'polaris.db'),
    UPLOAD_DIR: path.join(userData, 'uploads'),
    BACKUP_DIR: path.join(userData, 'backups'),
    REDIS_ENABLED: 'false',
    DEBUG: 'false',
    JWT_SECRET: getOrCreateJwtSecret(userData),
    CORS_ORIGINS: `http://127.0.0.1:${frontPort}`,
    WX_SCHEDULER_ENABLED: 'false',
    PYTHONIOENCODING: 'utf-8',
  }

  log(`启动后端：${exe} ${args.join(' ')} (port=${backendPort})`)
  const child = spawn(exe, args, { env, cwd, windowsHide: true })

  child.stdout.on('data', (d) => log(String(d)))
  child.stderr.on('data', (d) => log(String(d)))
  child.on('exit', (code, signal) => log(`后端进程退出 code=${code} signal=${signal}`))

  let unexpectedExit = null
  child.on('exit', (code) => { unexpectedExit = code })

  async function waitReady({ timeoutMs = 60000, intervalMs = 400 } = {}) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (unexpectedExit !== null) throw new Error(`后端进程提前退出（code=${unexpectedExit}）`)
      try {
        const r = await fetch(`http://127.0.0.1:${backendPort}/health`)
        if (r.ok) return
      } catch { /* 尚未就绪 */ }
      await sleep(intervalMs)
    }
    throw new Error('后端启动超时（60s）')
  }

  function kill() {
    if (child.exitCode !== null || child.signalCode !== null) return
    if (process.platform === 'win32') {
      // 树杀：onedir exe / python 可能派生子进程
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
    } else {
      child.kill('SIGTERM')
      setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL')
      }, 3000)
    }
  }

  return { child, waitReady, kill, get exited() { return unexpectedExit !== null } }
}

module.exports = { startBackend }
