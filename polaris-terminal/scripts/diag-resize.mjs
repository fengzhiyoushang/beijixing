/**
 * 复现「非全屏（窗口缩放）时知识库量化图表错位/变形」
 *
 * 关键：问题出现在「窗口被缩放」的过程中，而不是首次加载。
 * 因此这里保持页面不刷新，连续改变窗口宽度，并测量每个 ECharts canvas
 * 的 CSS 尺寸 / 像素尺寸 是否与容器一致（不一致 = 图表被拉伸变形）。
 *
 * 用法： node scripts/diag-resize.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9355
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
const profile = join(tmpdir(), `edge-rs-${Date.now()}`)
const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  '--disable-extensions',   // 排除浏览器扩展干扰（上次的 TypeError 来自扩展）
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
const loadEvents = []
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

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

// 只测总览页；全程不刷新，靠 setDeviceMetricsOverride 模拟窗口缩放
await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 980, deviceScaleFactor: 1, mobile: false })
await goto(`${WEB}/`)
await sleep(6000)

/** 测量所有 .glow-chart：canvas 的 CSS 显示尺寸 vs 容器尺寸 */
const measure = () => ev(`(() => {
  const out = [];
  document.querySelectorAll('.glow-chart').forEach((el, i) => {
    const cv = el.querySelector('canvas');
    const r = el.getBoundingClientRect();
    const label = (el.closest('.card')?.querySelector('.card-title')?.innerText || el.parentElement?.innerText || '')
      .replace(/\\s+/g, ' ').trim().slice(0, 22);
    if (!cv) { out.push({ i, label, noCanvas: true }); return; }
    const cr = cv.getBoundingClientRect();
    out.push({
      i, label,
      boxW: Math.round(r.width), boxH: Math.round(r.height),
      cssW: Math.round(cr.width), cssH: Math.round(cr.height),
      attrW: cv.width, attrH: cv.height,
      // 偏差：canvas 显示尺寸与容器尺寸差 >2px 判定为不同步
      dw: Math.round(cr.width - r.width), dh: Math.round(cr.height - r.height),
      // 像素比：attrW / cssW 应等于 dpr(1)
      ratio: cv.width ? +(cv.width / Math.max(1, cr.width)).toFixed(2) : 0,
    });
  });
  return out;
})()`)

const widths = [1680, 1500, 1366, 1280, 1200, 1100, 1024, 1150, 1400, 1680]
console.log('窗口宽度序列（模拟拖拽缩放，页面不刷新）：', widths.join(' → '))
console.log('')
let problems = 0
for (const w of widths) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false })
  await sleep(1400)     // 留出 ResizeObserver + ECharts resize 的时间
  const m = await measure()
  const bad = m.filter((x) => x.noCanvas ? false : (Math.abs(x.dw) > 2 || Math.abs(x.dh) > 2))
  const kb = m.find((x) => x.label.includes('入库量'))
  console.log(`${String(w).padStart(4)}px  图表数=${m.length}  失配=${bad.length}` +
    (kb ? `  知识库图表[容器 ${kb.boxW}x${kb.boxH} canvas ${kb.cssW}x${kb.cssH} attr ${kb.attrW}x${kb.attrH} dpr比=${kb.ratio}]` : ''))
  if (bad.length) {
    problems += bad.length
    bad.slice(0, 4).forEach((b) => console.log(`        ⚠ #${b.i}「${b.label}」容器 ${b.boxW}x${b.boxH} → canvas ${b.cssW}x${b.cssH}（Δ ${b.dw},${b.dh}）`))
  }
  if (w === 1200 || w === 1024) {
    await shot(`diag-resize-${w}.png`)
    // 知识库卡片局部大图
    const clip = await ev(`(() => {
      const el = document.querySelector('.kb-body'); if (!el) return null;
      const c = el.closest('.card').getBoundingClientRect();
      return JSON.stringify({ x: Math.max(0,c.x), y: Math.max(0,c.y), width: c.width, height: c.height });
    })()`)
    if (clip) {
      const c = JSON.parse(clip)
      const r = await send('Page.captureScreenshot', { format: 'png', clip: { ...c, scale: 2 } })
      writeFileSync(join(OUT, `diag-kbcard-${w}.png`), Buffer.from(r.data, 'base64'))
    }
  }
}

console.log(`\n失配累计：${problems}`)

// 额外：检查 ResizeObserver 数量与实例是否泄漏（echarts 实例数应等于图表数）
const inst = await ev(`(() => {
  const els = [...document.querySelectorAll('.glow-chart')];
  const withAttr = els.filter(e => e.getAttribute('_echarts_instance_')).length;
  return { charts: els.length, withAttr };
})()`)
console.log(`图表容器 ${inst.charts} 个，已绑定 echarts 实例 ${inst.withAttr} 个`)

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
