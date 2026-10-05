/**
 * 校验「已打包进 release / resources 的前端产物」是否包含两批修复。
 * 不启动 Electron 窗口（无交互桌面时会节流卡住），改为：
 *   ① 起一个静态服务器指向 release/win-unpacked/resources/dist
 *   ② 用 headless Edge 打开它（可与真实后端通信）
 *   ③ 跑与 verify-round2 相同的功能断言
 *
 * 用法： node scripts/verify-packaged-dist.mjs
 */
import { createServer } from 'node:http'
import { existsSync, readFileSync, mkdirSync, rmSync, writeFileSync, statSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { extname, join, normalize } from 'node:path'
import { tmpdir } from 'node:os'

const ROOT = 'F:\\deepseek harness  wenjian'
const DIST = join(ROOT, 'polaris-desktop', 'release', 'win-unpacked', 'resources', 'dist')
const API = 'http://127.0.0.1:8000'
const STATIC_PORT = 5399
const CDP_PORT = 9440
const OUT = join(ROOT, 'polaris-terminal', 'docs')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

if (!existsSync(join(DIST, 'index.html'))) { console.error('✗ 未找到打包 dist：' + DIST); process.exit(2) }

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
  '.woff2': 'font/woff2', '.woff': 'font/woff' }

// 静态服务器：静态文件 + /api 与 /health 反向代理到真实后端
const srv = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname.startsWith('/api') || url.pathname === '/health') {
    try {
      const body = await new Promise((resolve) => {
        const chunks = []
        req.on('data', (c) => chunks.push(c))
        req.on('end', () => resolve(Buffer.concat(chunks)))
      })
      const r = await fetch(API + req.url, {
        method: req.method,
        headers: { ...req.headers, host: new URL(API).host },
        body: ['GET', 'HEAD'].includes(req.method) ? undefined : body,
      })
      res.writeHead(r.status, { 'content-type': r.headers.get('content-type') || 'application/json' })
      res.end(Buffer.from(await r.arrayBuffer()))
    } catch (e) {
      res.writeHead(502); res.end(JSON.stringify({ detail: String(e.message) }))
    }
    return
  }
  let p = url.pathname === '/' ? '/index.html' : url.pathname
  const file = normalize(join(DIST, p))
  if (!file.startsWith(DIST) || !existsSync(file) || statSync(file).isDirectory()) {
    // SPA 回退
    res.writeHead(200, { 'content-type': MIME['.html'] })
    res.end(readFileSync(join(DIST, 'index.html')))
    return
  }
  res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' })
  res.end(readFileSync(file))
})
await new Promise((r) => srv.listen(STATIC_PORT, '127.0.0.1', r))
console.log(`静态服务器（打包产物）：http://127.0.0.1:${STATIC_PORT}`)

const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-pkgd-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  '--disable-extensions', `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let t = null
for (let i = 0; i < 45 && !t; i++) {
  await sleep(300)
  try { t = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
}
const ws = new WebSocket(t.webSocketDebuggerUrl)
await new Promise((res) => ws.addEventListener('open', res))
let id = 0
const pending = new Map(); const loads = []; const exps = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return }
  if (m.method === 'Page.loadEventFired') loads.push(1)
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails
    const u = d.url || d.stackTrace?.callFrames?.[0]?.url || ''
    if (!/^chrome-extension:/.test(u)) exps.push((d.exception?.description || d.text || '').split('\n')[0].slice(0, 150))
  }
})
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method: m, params: p }))
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + m)) } }, 45000)
})
const ev = async (x) => {
  const r = await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval fail')
  return r.result?.value
}
async function goto(url) {
  loads.length = 0
  await send('Page.navigate', { url })
  const s = Date.now()
  while (Date.now() - s < 25000) { if (loads.length) return; await sleep(70) }
}
const shot = async (n) => {
  try { const r = await send('Page.captureScreenshot', { format: 'png' })
    writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64')) } catch {}
}
const clickText = (sel, txt) => ev(`(() => {
  const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => (e.innerText||'').includes(${JSON.stringify(txt)}));
  if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true;
})()`)

const results = []
const rec = (no, name, ok, detail) => {
  results.push({ no, name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} [${no}] ${name}${detail ? '  → ' + detail : ''}`)
}

await send('Page.enable'); await send('Runtime.enable')

// 登录（走我们自己的代理）
const lg = await (await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})).json()
await goto(`http://127.0.0.1:${STATIC_PORT}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(lg.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(lg.user))});`)

console.log('\n── 打包产物：第二批修复 ──')

/* ① 系统设置合并 */
await goto(`http://127.0.0.1:${STATIC_PORT}/settings`); await sleep(6500)
const s1 = await ev(`(() => {
  const p = [...document.querySelectorAll('.card')].find(c => (c.innerText||'').includes('个性化外观'));
  if (!p) return { missing: true };
  const c = p.querySelector('.p-ctrl'), v = p.querySelector('.p-preview');
  const cr = c?.getBoundingClientRect(), vr = v?.getBoundingClientRect();
  return { merged: (p.innerText||'').includes('主题强调色') && (p.innerText||'').includes('光晕配色'),
           gap: (cr && vr) ? Math.abs(Math.round(cr.height - vr.height)) : 999,
           pageH: document.documentElement.scrollHeight,
           accent: p.querySelectorAll('.accent-btn').length,
           presets: p.querySelectorAll('.bg-preset').length,
           sliders: p.querySelectorAll('.bg-slider').length };
})()`)
rec('①-1', '强调色 + 背景外观已合并', !s1.missing && s1.merged)
rec('①-2', '左右两栏等高（无空白）', s1.gap <= 60, `高度差 ${s1.gap}px`)
rec('①-3', '页面紧凑（<1200px）', s1.pageH < 1200, `总高 ${s1.pageH}px（原 1957px）`)
rec('①-4', '控件齐全', s1.accent >= 4 && s1.presets >= 4 && s1.sliders >= 3,
  `${s1.accent}/${s1.presets}/${s1.sliders}`)
await shot('pkg2-settings.png')

/* ③ 学期弹窗 */
await goto(`http://127.0.0.1:${STATIC_PORT}/courses`); await sleep(6500)
await clickText('button', '学期管理'); await sleep(2500)
const s3 = await ev(`(() => {
  const m = document.querySelector('.n-modal'); if (!m) return { noModal: true };
  const items = [...m.querySelectorAll('.sf-item')].map(fi => {
    const lb = fi.querySelector('.sf-label'), inp = fi.querySelector('.n-input, .n-input-number');
    const lr = lb?.getBoundingClientRect(), ir = inp?.getBoundingClientRect();
    return { label: (lb?.innerText||'').trim(), w: ir ? Math.round(ir.width) : null,
             ov: (lr && ir) ? lr.bottom > ir.top + 2 : false };
  });
  return { items, ovs: items.filter(x => x.ov).length,
           btn: !!([...m.querySelectorAll('button')].find(b => /保存修改|创建学期/.test(b.innerText||''))) };
})()`)
const wk = s3.items?.find((x) => x.label?.includes('总周数'))
rec('③-1', '总周数输入框宽度正常', wk && wk.w >= 70, `${wk?.w}px（原 23px）`)
rec('③-2', '标签无重叠', s3.ovs === 0, `${s3.ovs} 处`)
rec('③-3', '保存/创建按钮可见', s3.btn)
await shot('pkg2-semester.png')
await ev(`document.querySelector('.n-modal .n-base-close')?.click()`); await sleep(900)

/* ④ 空闲预测 */
await goto(`http://127.0.0.1:${STATIC_PORT}/classroom`); await sleep(8000)
const s4 = await ev(`(() => {
  const c = [...document.querySelectorAll('.card')].find(x => (x.innerText||'').includes('空闲预测推荐'));
  if (!c) return { missing: true };
  const r = c.getBoundingClientRect();
  let bottom = r.top; [...c.children].forEach(k => bottom = Math.max(bottom, k.getBoundingClientRect().bottom));
  return { slack: Math.round(r.bottom - bottom),
           hasEmpty: !!c.querySelector('.pred-empty'),
           free: c.querySelectorAll('.pf-item').length,
           ops: c.querySelectorAll('.pe-ops button').length };
})()`)
rec('④-1', '空闲预测不再整块空白', !s4.missing && (s4.hasEmpty || s4.free > 0))
rec('④-2', '无快照时给出推算的教室', s4.free > 0, `${s4.free} 间`)
rec('④-3', '底部留白很小', s4.slack <= 40, `${s4.slack}px（原 807px）`)
await shot('pkg2-prediction.png')

/* ② 考研曲线 */
await goto(`http://127.0.0.1:${STATIC_PORT}/kaoyan`); await sleep(8000)
const s2 = await ev(`({
  ind: !!document.body.innerText.includes('行业分布与就业率'),
  emp: !!document.body.innerText.includes('主要就业单位与岗位'),
  canvas: document.querySelectorAll('canvas').length,
  cards: document.querySelectorAll('.emp-card').length,
  lines: !!document.body.innerText.includes('历年录取分数线')
})`)
rec('②-1', '历年录取分数线 + 曲线图', s2.lines && s2.canvas >= 2, `canvas ${s2.canvas}`)
rec('②-2', '行业分布与就业单位齐全', s2.ind && s2.emp && s2.cards > 0, `单位卡 ${s2.cards}`)
await shot('pkg2-kaoyan.png')

const uniq = [...new Set(exps)]
rec('⑤', '打包产物无未捕获异常', uniq.length === 0, uniq.length ? uniq[0] : '无')

ws.close(); child.kill(); srv.close()
try { rmSync(profile, { recursive: true, force: true }) } catch {}

const bad = results.filter((r) => !r.ok)
console.log('\n' + '═'.repeat(58))
console.log(`打包产物验证：共 ${results.length} 项，通过 ${results.length - bad.length}，失败 ${bad.length}`)
if (bad.length) { bad.forEach((r) => console.log(`  ✗ [${r.no}] ${r.name}${r.detail ? ' → ' + r.detail : ''}`)) }
console.log('截图：docs/pkg2-*.png')
process.exit(bad.length ? 1 : 0)
