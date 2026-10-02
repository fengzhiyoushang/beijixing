/*
 * Electron 主进程入口：
 * 单实例锁 → 探测空闲端口 → 启动后端子进程 → 等待 /health → 起本地静态/代理服务
 * → BrowserWindow.loadURL(http://127.0.0.1:<frontPort>) → 退出时优雅清理。
 */
const { app, BrowserWindow, dialog, ipcMain, shell, Menu } = require('electron')
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
  // 精简菜单（保留复制粘贴/刷新/开发者工具，便于桌面使用）
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {
      label: '编辑',
      submenu: [
        { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
        { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' },
      ],
    },
    {
      label: '视图',
      submenu: [{ role: 'reload' }, { role: 'forceReload' }, { role: 'toggleDevTools' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }],
    },
    { label: '窗口', submenu: [{ role: 'minimize' }, { role: 'close' }] },
  ]))

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

  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: '北极星 · 个人战略终端',
    backgroundColor: '#121212',
    show: false,
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

  // 加载失败兜底（dist 未构建等）
  win.webContents.on('did-fail-load', (_e, code, desc) => {
    if (code !== -3) dialog.showErrorBox('页面加载失败', `${code} ${desc}\n日志：${logFile}`)
  })

  win.once('ready-to-show', () => win.show())
  await win.loadURL(`http://127.0.0.1:${frontPort}/`)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) win?.reload()
  })
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
