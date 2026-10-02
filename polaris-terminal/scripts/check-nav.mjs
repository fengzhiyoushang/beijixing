/**
 * 侧栏导航回归测试（开发工具）
 *
 * 复现并验证「点击菜单后内容区空白、需要刷新」的问题：
 * 使用 CDP 真实登录 → 依次点击每个侧栏菜单 → 统计内容区渲染长度 + 捕获控制台异常。
 *
 * 用法： node scripts/check-nav.mjs [apiBase] [webBase]
 */
import { spawn } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = process.argv[2] || 'http://127.0.0.1:8000'
const WEB = process.argv[3] || 'http://127.0.0.1:5200'
const PORT = 9334

const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
]
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const ROUTES = [
  ['/', '总览'],
  ['/courses', '课程表'],
  ['/notes', '事项备忘'],
  ['/classroom', '空教室'],
  ['/kaoyan', '发展规划'],
  ['/knowledge', '知识整理'],
  ['/finance', '资产财务'],
  ['/health', '健康管理'],
  ['/settings', '系统设置'],
  ['/', '回到总览'],
  ['/kaoyan', '再次进入发展规划'],
  ['/settings', '再次进入系统设置'],
]

async function login() {
  const resp = await fetch(`${API}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  if (!resp.ok) throw new Error(`登录失败 HTTP ${resp.status}`)
  return resp.json()
}

class CDP {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.events = []
    this.exceptions = []
    this.consoleErrors = []
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
        return
      }
      if (msg.method === 'Runtime.exceptionThrown') {
        const d = msg.params.exceptionDetails
        this.exceptions.push(`${d.text} ${d.exception?.description?.split('\n')[0] || ''}`.slice(0, 200))
      }
      if (msg.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(msg.params.type)) {
        const text = msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ')
        this.consoleErrors.push(`[${msg.params.type}] ${text}`.slice(0, 200))
      }
      if (msg.method) this.events.push(msg.method)
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
      }, 15000)
    })
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    return res.result?.value
  }

  async waitLoad(timeout = 12000) {
    const start = Date.now()
    while (Date.now() - start < timeout) {
      if (this.events.includes('Page.loadEventFired')) {
        this.events = this.events.filter((e) => e !== 'Page.loadEventFired')
        return true
      }
      await sleep(60)
    }
    return false
  }
}

const PROBE = `(() => {
  const c = document.querySelector('.content');
  const h2 = document.querySelector('.content h2, .content .card-title');
  return {
    len: c ? c.innerText.trim().length : -1,
    head: (h2 ? h2.innerText : (c ? c.innerText : '')).replace(/\\s+/g, ' ').slice(0, 44),
    url: location.pathname,
  };
})()`

async function main() {
  const data = await login()
  console.log(`✓ 登录成功：${data.user.nickname}`)
  const profile = join(tmpdir(), `edge-nav-${Date.now()}`)
  const edge = EDGE_CANDIDATES.find((p) => existsSync(p))
  if (!edge) throw new Error('未找到 Edge')

  const child = spawn(edge, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1600,1000', 'about:blank',
  ], { stdio: 'ignore' })

  let target = null
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(300)
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      target = list.find((t) => t.type === 'page')
    } catch { /* 等待就绪 */ }
  }
  if (!target) throw new Error('无法连接调试端口')

  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res)
    ws.addEventListener('error', rej)
  })
  const cdp = new CDP(ws)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')

  await cdp.send('Page.navigate', { url: `${WEB}/login` })
  await cdp.waitLoad()
  await cdp.eval(`localStorage.setItem('pl_token', ${JSON.stringify(data.access_token)});
                  localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(data.user))});`)
  await cdp.send('Page.navigate', { url: `${WEB}/` })
  await cdp.waitLoad()
  await sleep(4200)

  let bad = 0
  console.log('\n路由  期望       内容长度  渲染首行')
  console.log('─'.repeat(78))
  for (const [path, label] of ROUTES) {
    // 模拟真实点击侧栏（而非直接改 URL），复现「点击无响应」
    const clicked = await cdp.eval(`(() => {
      const links = [...document.querySelectorAll('.side a.item')];
      const link = links.find(a => a.getAttribute('href') === ${JSON.stringify(path)});
      if (!link) return false;
      link.click();
      return true;
    })()`)
    if (!clicked) {
      console.log(`✗ 未找到菜单 ${path}`)
      bad++
      continue
    }
    await sleep(1600)
    const probe = await cdp.eval(PROBE)
    const ok = probe.len > 60 && probe.url === path
    if (!ok) bad++
    console.log(
      `${ok ? '✓' : '✗'} ${label.padEnd(12, '　')} ${String(path).padEnd(10)} ` +
      `len=${String(probe.len).padStart(5)}  ${probe.head}`,
    )
  }

  console.log('\n── 控制台异常 / 错误 ──')
  const uniq = [...new Set([...cdp.exceptions, ...cdp.consoleErrors])]
  if (!uniq.length) console.log('（无）')
  uniq.slice(0, 12).forEach((e) => console.log('  ' + e))

  console.log(`\n${bad === 0 ? '✅ 全部路由点击后均正常渲染' : `❌ 有 ${bad} 个路由点击后未正常渲染`}`)

  ws.close()
  child.kill()
  try { rmSync(profile, { recursive: true, force: true }) } catch { /* 忽略 */ }
  process.exit(bad === 0 ? 0 : 1)
}

main().catch((err) => {
  console.error('✗ 失败：', err.message)
  process.exit(2)
})
