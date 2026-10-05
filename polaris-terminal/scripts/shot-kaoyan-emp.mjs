/**
 * 滚动到「行业分布与就业率 / 主要就业单位与岗位」并截图（考研页）
 * 用法： node scripts/shot-kaoyan-emp.mjs [school]
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9367
const OUT = 'docs'
const SCHOOL = process.argv[2] || '华中科技大学'
const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const lg = await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})
const auth = await lg.json()
const H = { Authorization: `Bearer ${auth.access_token}`, 'Content-Type': 'application/json' }

// 切换目标（保留原目标用于恢复）
const orig = await (await fetch(`${API}/api/v1/kaoyan/target`, { headers: H })).json()
await fetch(`${API}/api/v1/kaoyan/target`, { method: 'PUT', headers: H,
  body: JSON.stringify({ school: SCHOOL, major: '计算机科学与技术', degree_type: '学硕' }) })

mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-ky-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  '--disable-extensions', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1700,1100', 'about:blank'], { stdio: 'ignore' })

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
await goto(`${WEB}/kaoyan`)
await sleep(8000)

// 检查两张卡片
const info = await ev(`(() => {
  const cards = [...document.querySelectorAll('section.card')];
  const find = (txt) => cards.find(c => (c.innerText||'').includes(txt));
  const ind = find('行业分布与就业率'), emp = find('主要就业单位与岗位');
  const r = (el) => el ? (() => { const b = el.getBoundingClientRect(); return { top:+b.top.toFixed(0), h:+b.height.toFixed(0) }; })() : null;
  return {
    industry: r(ind), employer: r(emp),
    empCards: document.querySelectorAll('.emp-card').length,
    shareLabels: [...document.querySelectorAll('.rt-name')].length,
    posTags: document.querySelectorAll('.pos-tags .chip').length,
    note: (document.querySelector('.intel-src')||{}).innerText || '',
    isEstimate: document.body.innerText.includes('就业画像为公开信息估算') || document.body.innerText.includes('口径估算'),
  };
})()`)
console.log(`行业卡片：${info.industry ? `高 ${info.industry.h}px` : '缺失'}`)
console.log(`就业卡片：${info.employer ? `高 ${info.employer.h}px` : '缺失'}`)
console.log(`就业单位卡片数：${info.empCards}`)
console.log(`典型岗位标签数：${info.posTags}`)
console.log(`是否标注估算口径：${info.isEstimate}`)

// 滚动到就业卡片并截图整个区块（注意：滚动容器是 .content，不是 window）
const box = await ev(`(() => {
  const cards = [...document.querySelectorAll('section.card')];
  const ind = cards.find(c => (c.innerText||'').includes('行业分布与就业率'));
  if (!ind) return null;
  const row = ind.parentElement;                       // 该行的 grid 容器
  const scroller = document.querySelector('.content') || document.scrollingElement;
  const r = row.getBoundingClientRect();
  const scRect = scroller.getBoundingClientRect();
  // 让该行顶部对齐滚动容器顶部（留 16px 余量）
  scroller.scrollTop += (r.top - scRect.top) - 16;
  return JSON.stringify({ rowH: Math.round(r.height), scrollTop: Math.round(scroller.scrollTop) });
})()`)
await sleep(1800)
const r = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(join(OUT, 'fix-kaoyan-employment.png'), Buffer.from(r.data, 'base64'))
if (box) {
  const b = JSON.parse(box)
  console.log(`滚动到就业区块：高度 ${b.rowH}px，scrollTop=${b.scrollTop}`)
  const r2 = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, 'fix-kaoyan-employment.png'), Buffer.from(r2.data, 'base64'))
}

// 恢复原目标
if (orig?.school) {
  await fetch(`${API}/api/v1/kaoyan/target`, { method: 'PUT', headers: H,
    body: JSON.stringify({ school: orig.school, major: orig.major,
                           degree_type: orig.degree_type || '学硕' }) })
  console.log(`↺ 已恢复目标院校：${orig.school}`)
}
ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log('截图：docs/fix-kaoyan-employment.png / -zoom.png')
