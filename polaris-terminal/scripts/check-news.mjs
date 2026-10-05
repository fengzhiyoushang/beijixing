/**
 * 新闻资讯「科技分类点击无内容」端到端复现（CDP）
 *
 * 流程：真实登录 → 进入 /news → 点击「科技」分类 → 等待列表 →
 *      真实鼠标点击第一张卡片 → 检查详情弹窗是否出现、正文是否为空，
 *      并捕获控制台异常 + 是否发生页面跳转（同页跳转 = 用户所说“同一个主页面”）。
 *
 * 用法： node scripts/check-news.mjs [apiBase] [webBase]
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = process.argv[2] || 'http://127.0.0.1:8000'
const WEB = process.argv[3] || 'http://127.0.0.1:5200'
const PORT = 9337
const OUT = 'docs'

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find((p) => existsSync(p))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.events = []
    this.exceptions = []; this.console = []
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id)
        m.error ? reject(new Error(m.error.message)) : resolve(m.result); return
      }
      if (m.method === 'Runtime.exceptionThrown') {
        this.exceptions.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text || '').split('\n')[0].slice(0, 200))
      }
      if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) {
        this.console.push(`[${m.params.type}] ` + m.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200))
      }
      if (m.method) this.events.push(m.method)
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((res, rej) => {
      this.pending.set(id, { resolve: res, reject: rej })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error('CDP timeout: ' + method)) } }, 20000)
    })
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    return r.result?.value
  }
  async waitLoad(t = 15000) {
    const s = Date.now()
    while (Date.now() - s < t) {
      if (this.events.includes('Page.loadEventFired')) { this.events = this.events.filter((e) => e !== 'Page.loadEventFired'); return true }
      await sleep(60)
    }
    return false
  }
  async clickSelector(sel) {
    const box = await this.eval(`(() => {
      const el = document.querySelector(${JSON.stringify(sel)});
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return JSON.stringify({ x: r.x + r.width/2, y: r.y + r.height/2 });
    })()`)
    if (!box) return false
    const { x, y } = JSON.parse(box)
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 })
    return true
  }
}

async function main() {
  const lg = await fetch(`${API}/api/v1/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  if (!lg.ok) throw new Error('后端登录失败 HTTP ' + lg.status)
  const auth = await lg.json()
  console.log('✓ 后端登录成功')

  mkdirSync(OUT, { recursive: true })
  const profile = join(tmpdir(), `edge-news-${Date.now()}`)
  const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--window-size=1600,1000', 'about:blank'],
    { stdio: 'ignore' })

  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    await sleep(300)
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
  }
  if (!t) throw new Error('无法连接浏览器')
  const ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej) })
  const cdp = new CDP(ws)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable')

  await cdp.send('Page.navigate', { url: `${WEB}/login` }); await cdp.waitLoad()
  await cdp.eval(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
                  localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

  console.log('→ 打开新闻资讯页')
  await cdp.send('Page.navigate', { url: `${WEB}/news` }); await cdp.waitLoad()
  await sleep(4000)
  const base = await cdp.eval(`({ url: location.href, cards: document.querySelectorAll('.card').length })`)
  console.log(`  初始：url=${base.url} 卡片=${base.cards}`)

  console.log('→ 点击「科技」分类')
  const clickedCat = await cdp.eval(`(() => {
    const b = [...document.querySelectorAll('.cat')].find(x => x.innerText.includes('科技'));
    if (!b) return false; b.click(); return true;
  })()`)
  if (!clickedCat) throw new Error('未找到「科技」分类按钮')
  await sleep(3500)

  const afterCat = await cdp.eval(`({
    url: location.href,
    cards: document.querySelectorAll('article.card').length,
    hero: !!document.querySelector('.hero'),
    firstTitle: (document.querySelector('article.card .c-title')||{}).innerText || '',
    empty: !!document.querySelector('.empty')
  })`)
  console.log(`  切换后：url=${afterCat.url} 文章卡=${afterCat.cards} 头条卡=${afterCat.hero}`)
  console.log(`  首条标题：${afterCat.firstTitle || '(无)'}`)
  const shot1 = await cdp.send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, 'news-tech-list.png'), Buffer.from(shot1.data, 'base64'))

  console.log('→ 真实鼠标点击第一张文章卡')
  const ok = await cdp.clickSelector('article.card')
  if (!ok) throw new Error('页面没有可点击的文章卡（列表为空 → 即“点进去没内容”）')
  await sleep(3000)

  const afterClick = await cdp.eval(`({
    url: location.href,
    modal: !!document.querySelector('.n-modal'),
    title: (document.querySelector('.d-title')||{}).innerText || '',
    contentLen: ((document.querySelector('.d-content')||{}).innerText || '').trim().length,
    loading: !!document.querySelector('.d-load'),
    errText: (document.querySelector('.n-message')||{}).innerText || ''
  })`)
  console.log(`  点击后：url=${afterClick.url}`)
  console.log(`  弹窗=${afterClick.modal} 标题「${afterClick.title}」正文长度=${afterClick.contentLen} 加载中=${afterClick.loading}`)
  if (afterClick.errText) console.log(`  页面提示：${afterClick.errText}`)
  const shot2 = await cdp.send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, 'news-tech-detail.png'), Buffer.from(shot2.data, 'base64'))

  console.log('\n── 控制台异常 ──')
  const uniq = [...new Set([...cdp.exceptions, ...cdp.console])]
  uniq.slice(0, 12).forEach((e) => console.log('  ' + e))
  if (!uniq.length) console.log('  （无）')

  let verdict = []
  if (afterCat.url !== base.url.split('?')[0] && !afterCat.url.includes('/news')) verdict.push('分类点击后离开了新闻页')
  if (afterCat.cards === 0 && !afterCat.hero) verdict.push('科技分类列表为空')
  if (!afterClick.modal) verdict.push('点击卡片未打开详情弹窗')
  if (afterClick.modal && afterClick.contentLen === 0 && !afterClick.loading) verdict.push('详情弹窗正文为空')

  ws.close(); child.kill()
  try { rmSync(profile, { recursive: true, force: true }) } catch {}

  if (verdict.length) { console.log('\n❌ 问题复现：' + verdict.join('；')); process.exit(1) }
  console.log('\n✅ 科技分类点击正常：列表有内容、详情弹窗有正文')
}

main().catch((e) => { console.error('✗ 失败：', e.message); process.exit(2) })
