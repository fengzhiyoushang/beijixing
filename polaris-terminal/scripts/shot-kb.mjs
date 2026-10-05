/**
 * 知识库量化卡片在非全屏宽度下的视觉验证：滚动到卡片并截图 + 结构化测量
 * 用法： node scripts/shot-kb.mjs [widths...]
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9359
const OUT = 'docs'
const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const WIDTHS = (process.argv.slice(2).map(Number).filter(Boolean).length
  ? process.argv.slice(2).map(Number).filter(Boolean) : [1680, 1366, 1200, 1024])

const lg = await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})
const auth = await lg.json()
mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-kb-${Date.now()}`)
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
let id = 0; const pending = new Map(); const loadEvents = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return }
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

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

for (const w of WIDTHS) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 2, mobile: false })
  await goto(`${WEB}/`)
  await sleep(5500)
  // 滚动到知识库卡片
  const ok = await ev(`(() => {
    const kb = document.querySelector('.kb-body'); if (!kb) return false;
    const card = kb.closest('.card');
    card.scrollIntoView({ block: 'center' });
    return true;
  })()`)
  await sleep(2200)
  const m = await ev(`(() => {
    const kb = document.querySelector('.kb-body');
    if (!kb) return { missing: true };
    const card = kb.closest('.card');
    const cr = card.getBoundingClientRect();
    const kids = [...kb.children].map((c, i) => {
      const r = c.getBoundingClientRect();
      return { i, x: +r.x.toFixed(0), y: +r.y.toFixed(0), w: +r.width.toFixed(0), h: +r.height.toFixed(0),
               right: +r.right.toFixed(0), txt: (c.innerText||'').replace(/\\n/g,'/').slice(0,14) };
    });
    const rows = {};
    kids.forEach(k => { const key = Math.round(k.y/14); (rows[key] ||= []).push(k); });
    let overlap = 0;
    Object.values(rows).forEach(g => { for (let a=0;a<g.length;a++) for (let b=a+1;b<g.length;b++) {
      if (g[a].right > g[b].x+1 && g[b].right > g[a].x+1) overlap++; } });
    const canvas = kb.querySelector('canvas');
    const cvr = canvas ? canvas.getBoundingClientRect() : null;
    return { kids, overlap, cardOverflow: kids.filter(k => k.right > cr.right-1 || k.x < cr.left+1).length,
             cols: getComputedStyle(kb).gridTemplateColumns,
             canvas: cvr ? { w:+cvr.width.toFixed(0), h:+cvr.height.toFixed(0) } : null,
             chartBox: (() => { const c = kb.querySelector('.glow-chart'); if (!c) return null;
               const r = c.getBoundingClientRect(); return { w:+r.width.toFixed(0), h:+r.height.toFixed(0) }; })() };
  })()`)
  console.log(`\n${w}px  列=[${m.cols}]  同行重叠=${m.overlap}  卡片溢出=${m.cardOverflow}`)
  if (m.chartBox) console.log(`      图表容器 ${m.chartBox.w}x${m.chartBox.h}  canvas ${m.canvas?.w}x${m.canvas?.h}` +
    (m.chartBox.w === m.canvas?.w && m.chartBox.h === m.canvas?.h ? '  ✓ 同步' : '  ⚠ 不同步'))
  ;(m.kids || []).forEach(k => console.log(`      #${k.i} y=${k.y} x=${k.x}..${k.right} w=${k.w} h=${k.h} 「${k.txt}」`))

  const r = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, `kb-verified-${w}.png`), Buffer.from(r.data, 'base64'))
}

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log('\n截图：docs/kb-verified-*.png')
