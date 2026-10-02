/**
 * 端到端截图验证脚本（开发工具）
 *
 * 作用：用 headless 浏览器真实登录后端 → 注入 token → 逐页截图，
 *      证明「前端已接入真实接口」而不是 mock。
 *
 * 用法： node scripts/capture.mjs [apiBase] [webBase]
 *   默认 apiBase=http://127.0.0.1:8000  webBase=http://127.0.0.1:5200
 * 产物： docs/shot-<page>.png
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = process.argv[2] || 'http://127.0.0.1:8000'
const WEB = process.argv[3] || 'http://127.0.0.1:5200'
const PORT = 9333
const OUT = 'docs'

const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function login() {
  const resp = await fetch(`${API}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  if (!resp.ok) throw new Error(`登录失败 HTTP ${resp.status}：${await resp.text()}`)
  const data = await resp.json()
  console.log(`✓ 后端登录成功：${data.user.nickname}（${data.user.username}）`)
  return data
}

class CDP {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.events = []
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
      } else if (msg.method) {
        this.events.push(msg.method)
      }
    })
  }

  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`CDP 超时：${method}`))
        }
      }, 20000)
    })
  }

  async waitEvent(method, timeout = 15000) {
    const start = Date.now()
    while (Date.now() - start < timeout) {
      if (this.events.includes(method)) {
        this.events = this.events.filter((e) => e !== method)
        return true
      }
      await sleep(80)
    }
    return false
  }
}

async function main() {
  const data = await login()
  mkdirSync(OUT, { recursive: true })
  const profile = join(tmpdir(), `edge-polaris-${Date.now()}`)

  const edge = EDGE_CANDIDATES.find((p) => existsSync(p))
  if (!edge) throw new Error('未找到 Edge 可执行文件')

  const child = spawn(edge, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1600,1000', 'about:blank',
  ], { stdio: 'ignore', detached: false })
  console.log('· 启动 headless 浏览器…')

  let target = null
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(300)
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      target = list.find((t) => t.type === 'page')
    } catch {
      /* 尚未就绪 */
    }
  }
  if (!target) throw new Error(`无法连接浏览器调试端口 ${PORT}`)

  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve)
    ws.addEventListener('error', reject)
  })
  const cdp = new CDP(ws)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  console.log('✓ 已连接 CDP')

  // 1) 先打开登录页，注入 token（等价于用户登录后的状态）
  await cdp.send('Page.navigate', { url: `${WEB}/login` })
  await cdp.waitEvent('Page.loadEventFired')
  await sleep(600)
  await cdp.send('Runtime.evaluate', {
    expression: `localStorage.setItem('pl_token', ${JSON.stringify(data.access_token)});
                 localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(data.user))});`,
  })
  console.log('✓ 已注入登录态')

  // 2) 登录页截图（未注入时会被守卫拦截，先截一张登录页）
  await cdp.send('Runtime.evaluate', { expression: `localStorage.clear()` })
  await cdp.send('Page.navigate', { url: `${WEB}/login` })
  await cdp.waitEvent('Page.loadEventFired')
  await sleep(1200)
  await shoot(cdp, 'login', '登录页')

  // 3) 重新注入并逐页截图
  await cdp.send('Runtime.evaluate', {
    expression: `localStorage.setItem('pl_token', ${JSON.stringify(data.access_token)});
                 localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(data.user))});`,
  })
  const pages = [
    ['', 'dashboard', 4200],
    ['/courses', 'courses', 2600],
    ['/notes', 'notes', 2600],
    ['/kaoyan', 'kaoyan', 2600],
    ['/knowledge', 'knowledge', 2600],
    ['/finance', 'finance', 2600],
    ['/health', 'health', 2600],
    ['/settings', 'settings', 2600],
  ]
  for (const [path, name, wait] of pages) {
    await cdp.send('Page.navigate', { url: `${WEB}${path}` })
    await cdp.waitEvent('Page.loadEventFired')
    await sleep(wait)
    await shoot(cdp, name, `页面 ${path || '/'}`)
  }

  // 3.5) 打开 AI 助手面板并截图（验证悬浮窗样式）
  await cdp.send('Page.navigate', { url: `${WEB}/` })
  await cdp.waitEvent('Page.loadEventFired')
  await sleep(3000)
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.fab')?.click()`,
  })
  await sleep(1200)
  await shoot(cdp, 'ai-panel', 'AI 助手悬浮窗')

  // 3.6) 新建待办事项弹窗（含自主时间设置）
  await cdp.send('Runtime.evaluate', { expression: `document.querySelector('.act.close')?.click()` })
  await sleep(500)
  // 单个「＋ 新建」按钮 → 点开下拉菜单
  await cdp.send('Runtime.evaluate', { expression: `document.querySelector('.new-btn')?.click()` })
  await sleep(700)
  // 选择「新建待办事项」打开弹窗（用真实鼠标事件，避免下拉项点击不生效）
  const rect = await cdp.send('Runtime.evaluate', {
    expression: `(() => {
      const el = [...document.querySelectorAll('.n-dropdown-option')]
        .find(e => e.innerText.includes('新建待办事项'));
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return JSON.stringify({ x: r.x + r.width / 2, y: r.y + r.height / 2 });
    })()`,
    returnByValue: true,
  })
  if (rect.result.value) {
    const { x, y } = JSON.parse(rect.result.value)
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 })
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 })
  } else {
    console.log('  ! 未找到下拉项，跳过弹窗截图')
  }
  await sleep(1100)
  await shoot(cdp, 'new-task-modal', '新建待办事项弹窗（自主时间设置）')

  // 3.7) 关闭弹窗后取顶栏右上角特写（验证「＋ 新建」为单个按钮）
  await cdp.send('Runtime.evaluate', { expression: `document.querySelector('.n-base-close')?.click()` })
  await sleep(400)
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await sleep(600)
  const clipShot = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    clip: { x: 980, y: 0, width: 620, height: 96, scale: 2 },
  })
  writeFileSync(join(OUT, 'shot-topbar.png'), Buffer.from(clipShot.data, 'base64'))
  console.log('  ✓ 顶栏右上角（单按钮 ＋新建） → docs/shot-topbar.png')

  // 4) 校验页面是否渲染出真实数据（读取 DOM 文本）
  const check = await cdp.send('Runtime.evaluate', {
    expression: `document.body.innerText.replace(/\\s+/g,' ').slice(0, 400)`,
    returnByValue: true,
  })
  console.log('\n当前页面文本片段：\n' + check.result.value)

  ws.close()
  child.kill()
  try {
    rmSync(profile, { recursive: true, force: true })
  } catch {
    /* 忽略 */
  }
  console.log('\n✅ 截图完成，输出目录 docs/')
}

async function shoot(cdp, name, label) {
  const shot = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: true,
  })
  writeFileSync(join(OUT, `shot-${name}.png`), Buffer.from(shot.data, 'base64'))
  console.log(`  ✓ ${label} → docs/shot-${name}.png`)
}

main().catch((err) => {
  console.error('✗ 失败：', err.message)
  process.exit(1)
})
