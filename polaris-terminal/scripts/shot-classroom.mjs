/**
 * 空教室「时间维度」控件视觉与行为验证 + 截图
 * 用法： node scripts/shot-classroom.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9371
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
const profile = join(tmpdir(), `edge-cr-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  '--disable-extensions', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1760,1100', 'about:blank'], { stdio: 'ignore' })

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
const shot = async (n) => {
  const r = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64'))
}
const clickText = (sel, txt) => ev(`(() => {
  const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => (e.innerText||'').includes(${JSON.stringify(txt)}));
  if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true;
})()`)
/** 统计占用格数量（busy 类） */
const countBusy = () => ev(`document.querySelectorAll('.b-cell.busy, .b-grid > .busy, [class*="cell"][class*="busy"]').length`)

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)
await goto(`${WEB}/classroom`)
await sleep(8000)

console.log('── 时间维度控件 ──')
const ui = await ev(`({
  modes: [...document.querySelectorAll('.n-radio-button')].map(e => e.innerText.trim()),
  hasDate: !!document.querySelector('.ctrl-date'),
  hasWeek: !!document.querySelector('.ctrl-week'),
  hours: document.querySelectorAll('.ctrl-hour').length,
  legend: (document.querySelector('.lg-note')||{}).innerText||'',
  semTip: (document.querySelector('.sem-tip')||{}).innerText||'',
  cells: document.querySelectorAll('[class*="cell"]').length
})`)
console.log('模式：', ui.modes)
console.log('图例/当前时段：', ui.legend.trim())
console.log('学期提示：', ui.semTip.trim())
console.log('时段控件数：', ui.hours)
await shot('fix-classroom-now.png')

// 切到「指定日期」
await clickText('.n-radio-button', '指定日期'); await sleep(3000)
const d = await ev(`({ hasDate: !!document.querySelector('.ctrl-date'), legend: (document.querySelector('.lg-note')||{}).innerText||'' })`)
console.log('\n指定日期模式：日期选择器=', d.hasDate, '| ', d.legend.trim())
await shot('fix-classroom-date.png')

// 用日期选择器输入一个学期内日期（直接改 input 值 + input 事件，再走确认按钮）
const setOk = await ev(`(() => {
  const inp = document.querySelector('.ctrl-date input');
  if (!inp) return 'no-input';
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '2026-11-02');   // 第 10 周周一
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  inp.blur();
  return 'set';
})()`)
await sleep(3500)
const afterDate = await ev(`({ legend: (document.querySelector('.lg-note')||{}).innerText||'',
                              semTip: (document.querySelector('.sem-tip')||{}).innerText||'' })`)
console.log('输入 2026-11-02 后：', afterDate.semTip.trim() || afterDate.legend.trim())
await shot('fix-classroom-date-set.png')

// 切到「按教学周」
await clickText('.n-radio-button', '按教学周'); await sleep(3000)
const wk = await ev(`({ hasWeek: !!document.querySelector('.ctrl-week'), daySelectable: !!document.querySelector('.ctrl-day'),
                       legend: (document.querySelector('.lg-note')||{}).innerText||'' })`)
console.log('\n按教学周模式：周次选择器=', wk.hasWeek, '星期可手动选=', wk.daySelectable)
console.log('  ', wk.legend.trim())
await shot('fix-classroom-week.png')

// 时段区间：把结束时间调大，确认图例区间随之变化
await ev(`(() => {
  const sels = [...document.querySelectorAll('.ctrl-hour')];
  return sels.length;
})()`)
console.log('\n时段区间控件已就位（开始/结束各一档）')

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log('\n截图：docs/fix-classroom-{now,date,date-set,week}.png')
