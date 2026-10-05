/**
 * 定位 "v[w] is not a function" 未捕获异常 + 检查 kb-body 在窄窗口的真实布局
 * 用法： node scripts/diag-errors.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9351
const OUT = 'docs'
const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const lg = await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})
const auth = await lg.json()

mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-diag-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--window-size=1680,1000', 'about:blank'],
  { stdio: 'ignore' })

let t = null
for (let i = 0; i < 45 && !t; i++) {
  await sleep(300)
  try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
}
const ws = new WebSocket(t.webSocketDebuggerUrl)
await new Promise((res) => ws.addEventListener('open', res))
let id = 0
const pending = new Map()
const exceptions = []
const loadEvents = []
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails
    exceptions.push({
      text: d.text,
      desc: d.exception?.description || '',
      url: d.url, line: d.lineNumber, col: d.columnNumber,
      stack: (d.stackTrace?.callFrames || []).slice(0, 8).map((f) => `${f.functionName || '(anon)'} @ ${f.url}:${f.lineNumber}:${f.columnNumber}`),
    })
  }
  if (m.method === 'Page.loadEventFired') loadEvents.push(1)
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method, params }))
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)) } }, 30000)
})
const ev = async (e) => {
  const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval fail')
  return r.result?.value
}
async function goto(url) {
  loadEvents.length = 0
  await send('Page.navigate', { url })
  const s = Date.now()
  while (Date.now() - s < 20000) { if (loadEvents.length) return; await sleep(60) }
}
const shot = async (n, clip) => {
  const r = await send('Page.captureScreenshot', clip ? { format: 'png', clip: { ...clip, scale: 2 } } : { format: 'png' })
  writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64'))
}

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

// 逐页访问，定位异常来源
const pages = ['/', '/classroom', '/kaoyan', '/news', '/settings', '/knowledge', '/courses', '/notes', '/finance', '/health', '/bookmarks', '/ai']
for (const p of pages) {
  const before = exceptions.length
  await goto(`${WEB}${p}`)
  await sleep(4500)
  const n = exceptions.length - before
  console.log(`${n ? '⚠' : '✓'} ${p.padEnd(13)} 新增异常 ${n}`)
  if (n) {
    for (const e of exceptions.slice(before)) {
      console.log(`     ${e.text}: ${e.desc.split('\n')[0].slice(0, 120)}`)
      console.log(`     @ ${e.url}:${e.line}:${e.col}`)
      e.stack.forEach((s) => console.log('       ' + s))
    }
  }
}

// kb-body 真实布局（多个宽度）
console.log('\n── kb-body 布局实测 ──')
for (const w of [1680, 1440, 1280, 1200, 1100, 1024]) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 2, mobile: false })
  await goto(`${WEB}/`)
  await sleep(4200)
  const m = await ev(`(() => {
    const kb = document.querySelector('.kb-body');
    if (!kb) return { missing: true };
    const card = kb.closest('.card');
    const cr = card.getBoundingClientRect();
    const kids = [...kb.children].map((c, i) => {
      const r = c.getBoundingClientRect();
      const cs = getComputedStyle(c);
      return { i, x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1),
               right: +r.right.toFixed(1), bottom: +r.bottom.toFixed(1), txt: (c.innerText||'').replace(/\\n/g,'/').slice(0,16) };
    });
    // 只比较"同一行"（y 相近）元素的横向交叠 → 真正的内容重叠
    const rows = {};
    kids.forEach(k => { const key = Math.round(k.y/12); (rows[key] ||= []).push(k); });
    let realOverlap = 0; const pairs = [];
    Object.values(rows).forEach(g => {
      for (let a=0;a<g.length;a++) for (let b=a+1;b<g.length;b++) {
        if (g[a].right > g[b].x + 1 && g[b].right > g[a].x + 1) { realOverlap++; pairs.push([g[a].txt, g[b].txt]); }
      }
    });
    const cardOverflow = kids.filter(k => k.right > cr.right - 1 || k.x < cr.left + 1).length;
    return { kids, realOverlap, pairs, cardOverflow,
             gridCols: getComputedStyle(kb).gridTemplateColumns,
             hScroll: kb.scrollWidth > kb.clientWidth + 1,
             cardH: +cr.height.toFixed(1) };
  })()`)
  if (m.missing) { console.log(`  ${w}px: kb-body 缺失`); continue; }
  console.log(`  ${w}px  列=[${m.gridCols}]  子=${m.kids.length}  同行重叠=${m.realOverlap}  卡片溢出=${m.cardOverflow}  横向滚动=${m.hScroll}  卡片高=${m.cardH}`)
  m.kids.forEach(k => console.log(`      #${k.i} y=${k.y} x=${k.x}..${k.right} (w=${k.w}) 「${k.txt}」`))
  if (m.pairs.length) console.log('      重叠对：', JSON.stringify(m.pairs))
  if (w === 1200 || w === 1024) await shot(`diag-kb-${w}.png`)
}

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log(`\n异常总数：${exceptions.length}`)
