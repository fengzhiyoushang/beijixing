/*
 * Electron 主进程入口：
 * 单实例锁 → 探测空闲端口 → 启动后端子进程 → 等待 /health → 起本地静态/代理服务
 * → BrowserWindow.loadURL(http://127.0.0.1:<frontPort>) → 退出时优雅清理。
 */
const { app, BrowserWindow, dialog, ipcMain, shell, Menu, screen } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const { createLocalServer, pickFreePorts } = require('./local-server')
const { startBackend } = require('./backend-manager')

const REPO_ROOT = app.isPackaged ? '' : path.resolve(__dirname, '..', '..')
const userData = app.getPath('userData')
const logFile = path.join(userData, 'logs', 'backend.log')
fs.mkdirSync(path.dirname(logFile), { recursive: true })

let win = null
let backend = null
let server = null
let quitting = false

function blog(line) {
  fs.appendFile(logFile, `[${new Date().toISOString()}] ${line}\n`, () => {})
}

// ── 单实例：二次启动聚焦已有窗口 ──
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore()
      win.focus()
    }
  })
  app.whenReady().then(boot).catch(fatal)
}

async function boot() {
  // 去掉原生菜单栏（编辑/视图/窗口），内容顶到窗口最上方；
  // 常用快捷键（Ctrl+R 刷新、Ctrl+Shift+I 开发者工具、复制粘贴）仍可正常使用。
  Menu.setApplicationMenu(null)

  const [backendPort, frontPort] = await pickFreePorts(2)

  backend = startBackend({
    backendPort,
    frontPort,
    userData,
    repoRoot: REPO_ROOT,
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    logger: blog,
  })

  // 后端意外退出时提示（正常清理流程中不弹）
  backend.child.on('exit', (code) => {
    if (!quitting && code !== 0 && code !== null) {
      dialog.showErrorBox('后端服务异常退出', `后端进程意外退出（code=${code}）。\n日志：${logFile}`)
      cleanup()
      app.quit()
    }
  })

  await backend.waitReady()

  const distRoot = app.isPackaged
    ? path.join(process.resourcesPath, 'dist')
    : path.join(REPO_ROOT, 'polaris-terminal', 'dist')

  server = await createLocalServer({ frontPort, backendPort, distRoot })
  blog(`本地服务就绪：http://127.0.0.1:${frontPort} → 后端 :${backendPort}`)

  // 按当前显示器工作区自适应窗口尺寸：默认占 90%，居中，保留最小尺寸
  const wa = screen.getPrimaryDisplay().workAreaSize
  const winW = Math.max(1024, Math.min(1920, Math.round(wa.width * 0.9)))
  const winH = Math.max(700, Math.min(1200, Math.round(wa.height * 0.9)))
  win = new BrowserWindow({
    width: winW,
    height: winH,
    minWidth: 1024,
    minHeight: 700,
    center: true,
    show: false,
    autoHideMenuBar: true,
    title: '北极星 · 个人战略终端',
    backgroundColor: '#070a08',
    // 隐藏原生标题栏：内容顶到窗口最上方，右上角保留系统覆盖式窗口按钮
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#070a08',
      symbolColor: '#9aa8a0',
      height: 40,
    },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // 外链交给系统浏览器，不在应用内开新窗
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  // 主窗口禁止导航到外部站点（防止误把应用窗口跳到第三方页面）
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${frontPort}`)) {
      e.preventDefault()
      if (/^https?:\/\//.test(url)) shell.openExternal(url)
    }
  })

  // 加载失败兜底（dist 未构建等）
  let loadFailed = null
  win.webContents.on('did-fail-load', (_e, code, desc, url, isMainFrame) => {
    // code -3 = ERR_ABORTED：通常是并发跳转/重定向导致的中止，页面往往已经正常渲染，
    // 属良性事件，仅记日志，不弹窗、不退出。
    if (code === -3) {
      blog(`页面加载被中止（-3，良性）：${desc} ${url || ''}`)
      return
    }
    if (isMainFrame === false) return
    loadFailed = { code, desc }
    blog(`页面加载失败：${code} ${desc} ${url || ''}`)
  })

  win.once('ready-to-show', () => win.show())

  // loadURL 在 ERR_ABORTED(-3) 时也会 reject，若直接冒泡到 fatal() 会让
  // 一次瞬时中止演变成「启动失败」弹窗并退出应用。此处只对真正失败重试/报错。
  await loadFrontend(win, `http://127.0.0.1:${frontPort}/`, blog, () => loadFailed)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) win?.reload()
  })
}

/**
 * 加载前端页面，带一次重试。
 * 只有「确实没加载出来」才抛错（由 fatal 处理）；ERR_ABORTED 视为已成功。
 */
async function loadFrontend(win, url, log, getFail) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await win.loadURL(url)
      return
    } catch (err) {
      const msg = String(err?.message || err)
      const aborted = /ERR_ABORTED|\(-3\)/.test(msg)
      log(`loadURL 第 ${attempt} 次${aborted ? '被中止(-3)' : '失败'}：${msg}`)
      if (aborted && win.webContents.getURL().startsWith(url)) {
        // 已跳转到目标地址：实际加载成功，忽略这次中止
        log('页面实际已就绪，忽略本次中止')
        return
      }
      if (attempt === 2) {
        const f = getFail()
        throw new Error(`前端页面加载失败：${f ? `${f.code} ${f.desc}` : msg}`)
      }
      await new Promise((r) => setTimeout(r, 800))
    }
  }
}

function fatal(err) {
  blog(`致命错误：${err?.stack || err}`)
  dialog.showErrorBox('启动失败', String(err?.message || err))
  cleanup()
  app.quit()
}

function cleanup() {
  quitting = true
  try { backend?.kill() } catch { /* ignore */ }
  try { server?.close() } catch { /* ignore */ }
}

app.on('window-all-closed', () => {
  cleanup()
  app.quit()
})
app.on('before-quit', cleanup)
process.on('uncaughtException', (e) => { blog(`uncaughtException: ${e?.stack || e}`); fatal(e) })
process.on('exit', cleanup)

// ── 外部链接：渲染端经 IPC 请求用系统默认浏览器（Edge）打开 ──
// 沙箱预加载脚本拿不到 shell，必须在主进程执行
ipcMain.handle('open-external', async (_e, url) => {
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
    await shell.openExternal(url)
    return true
  }
  return false
})

// ── 原生"另存为"：渲染端把 blob 内容传回，主进程弹保存对话框写盘 ──
ipcMain.handle('save-blob', async (_e, { defaultName, data }) => {
  if (!win) return { saved: false }
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    defaultPath: defaultName || 'download',
  })
  if (canceled || !filePath) return { saved: false }
  fs.writeFileSync(filePath, Buffer.from(data))
  return { saved: true, path: filePath }
})
