/**
 * 前后对比：把「原版」知识库栅格 CSS 注入当前页面，量化它造成的错位/变形，
 * 用以证明问题③确实存在且已被修复。
 *
 * 原版规则（修复前）：
 *   .kb-body { grid-template-columns: 120px 130px 120px 1fr 1.2fr; gap:18px; }
 *   @media (max-width:1400px){ .kb-body{grid-template-columns:1fr 1fr 1fr} .kb-chart,.kb-tags{grid-column:span 3} }
 *
 * 用法： node scripts/compare-kb.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9363
const OUT = 'docs'
const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const OLD_CSS = `
.kb-body { display:grid !important; grid-template-columns:120px 130px 120px 1fr 1.2fr !important; gap:18px !important; align-items:center !important; }
.kb-chart, .kb-tags { min-width:0 !important; }
.tags { display:flex !important; flex-wrap:wrap !important; gap:6px !important; max-height:none !important; overflow:visible !important; }
.kb-stat .num-big { font-size:inherit !important; white-space:normal !important; overflow:visible !important; max-width:none !important; }
@media (max-width:1400px){
  .kb-body { grid-template-columns:1fr 1fr 1fr !important; }
  .kb-chart, .kb-tags { grid-column:span 3 !important; }
}
`

const lg = await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})
const auth = await lg.json()
mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-cmp-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  '--disable-extensions', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let t = null
for (let i = 0; i < 45 && !t; i++) {
  await sleep(300)
  try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
}
const ws = new WebSocket(t.webSocketDebuggerUrl)
await new Promise((res) => ws.addEventListener('open', res))
let id = 0
const pending = new Map()
const loadEvents = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id)
    m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return
  }
  if (m.method === 'Page.loadEventFired') loadEvents.push(1)
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method, params }))
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)) } }, 30000)
})
const ev = async (x) => {
  const r = await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval fail')
  return r.result?.value
}
async function goto(url) {
  loadEvents.length = 0
  await send('Page.navigate', { url })
  const s = Date.now()
  while (Date.now() - s < 20000) { if (loadEvents.length) return; await sleep(60) }
}
const shot = async (n) => {
  const r = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64'))
}

const MEASURE = `(() => {
  const kb = document.querySelector('.kb-body');
  if (!kb) return { missing: true };
  const card = kb.closest('.card');
  const cr = card.getBoundingClientRect();
  const kids = [...kb.children].map((c, i) => {
    const r = c.getBoundingClientRect();
    return { i, x:+r.x.toFixed(0), y:+r.y.toFixed(0), w:+r.width.toFixed(0), h:+r.height.toFixed(0),
             right:+r.right.toFixed(0), bottom:+r.bottom.toFixed(0),
             txt:(c.innerText||'').replace(/\\n/g,'/').slice(0,13) };
  });
  const rows = {};
  kids.forEach(k => { const key = Math.round(k.y/14); (rows[key] ||= []).push(k); });
  let overlap = 0; const pairs = [];
  Object.values(rows).forEach(g => { for (let a=0;a<g.length;a++) for (let b=a+1;b<g.length;b++) {
    if (g[a].right > g[b].x+1 && g[b].right > g[a].x+1) { overlap++; pairs.push([g[a].txt, g[b].txt]); } } });
  const cc = kb.querySelector('canvas');
  const cvr = cc ? cc.getBoundingClientRect() : null;
  const cb = kb.querySelector('.glow-chart');
  const cbr = cb ? cb.getBoundingClientRect() : null;
  return {
    cols: getComputedStyle(kb).gridTemplateColumns,
    overlap, pairs,
    cardOverflow: kids.filter(k => k.right > cr.right-1 || k.x < cr.left+1).length,
    cardBottomOverflow: kids.filter(k => k.bottom > cr.bottom-1).length,
    canvasDelta: (cvr && cbr) ? { dw: Math.round(cvr.width-cbr.width), dh: Math.round(cvr.height-cbr.height) } : null,
    badgeOverflow: (() => { const b = card.querySelector('.card-head .chip'); if(!b) return null;
      const r = b.getBoundingClientRect(); return r.right > cr.right-1 || r.left < cr.left+1; })(),
    kids,
  };
})()`

await send('Page.enable')
await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

const WIDTHS = [1400, 1366, 1200]
console.log('对比：当前（已修复） vs 原版 CSS 注入\n')
for (const w of WIDTHS) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false })
  await goto(`${WEB}/`)
  await sleep(5500)
  await ev(`(() => { const k = document.querySelector('.kb-body'); if (k) k.closest('.card').scrollIntoView({block:'center'}); })()`)
  await sleep(1800)

  const now = await ev(MEASURE)
  // 注入原版 CSS
  await ev(`(() => {
    let s = document.getElementById('__oldkb');
    if (!s) { s = document.createElement('style'); s.id = '__oldkb'; document.head.appendChild(s); }
    s.textContent = ${JSON.stringify(OLD_CSS)};
    return true;
  })()`)
  await sleep(2000)
  const old = await ev(MEASURE)

  const fmt = (m) => m.missing ? 'kb-body 缺失'
    : `列=[${m.cols}] 同行重叠=${m.overlap} 卡片左右溢出=${m.cardOverflow} 底部溢出=${m.cardBottomOverflow} canvasΔ=${m.canvasDelta ? `${m.canvasDelta.dw},${m.canvasDelta.dh}` : '-'}`
  console.log(`${w}px`)
  console.log(`   修复后：${fmt(now)}`)
  console.log(`   原  版：${fmt(old)}`)
  const worse = old.overlap > now.overlap || old.cardOverflow > now.cardOverflow || old.cardBottomOverflow > now.cardBottomOverflow
  console.log(`   → 原版是否更差：${worse ? '是（证明修复有效）' : '否（该宽度下差异不明显）'}`)
  if (old.pairs?.length) console.log(`     原版重叠对：${JSON.stringify(old.pairs)}`)

  await shot(`kb-before-${w}.png`)                 // 当前是原版样式
  await ev(`document.getElementById('__oldkb')?.remove()`)
  await sleep(1200)
  await shot(`kb-after-${w}.png`)
  console.log('')
}

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log('截图：docs/kb-before-*.png（原版） / docs/kb-after-*.png（修复后）')
