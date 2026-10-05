/**
 * 复现并定位用户反馈的 4 个问题（截图 + 结构化测量）
 *
 * ① 系统设置：主题强调色与背景外观分卡、页面留白过多
 * ③ 学期管理弹窗：总周数输入框过窄、保存无反应
 * ④ 课程表 PDF 上传报错、空闲预测推荐不显示
 *
 * 用法： node scripts/diag-issues.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9420
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
const profile = join(tmpdir(), `edge-di ${Date.now()}`)
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
let id = 0; const pending = new Map(); const loads = []; const exps = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return }
  if (m.method === 'Page.loadEventFired') loads.push(1)
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails
    const u = d.url || d.stackTrace?.callFrames?.[0]?.url || ''
    if (!/^chrome-extension:/.test(u)) exps.push((d.exception?.description || d.text || '').split('\n')[0].slice(0, 160))
  }
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method, params }))
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)) } }, 40000)
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
  try {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64'))
  } catch (e) { console.log(`  (截图失败 ${n})`) }
}
const clickText = (sel, txt) => ev(`(() => {
  const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => (e.innerText||'').includes(${JSON.stringify(txt)}));
  if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true;
})()`)

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

/* ═══ ① 系统设置布局 ═══ */
console.log('═══ ① 系统设置：分卡与留白 ═══')
await goto(`${WEB}/settings`)
await sleep(6000)
const st = await ev(`(() => {
  const cards = [...document.querySelectorAll('.card')];
  const info = cards.map((c, i) => {
    const r = c.getBoundingClientRect();
    const t = (c.querySelector('.card-title')||{}).innerText || '';
    // 卡片内最后一个子元素的底部 → 估算内容高度
    const kids = [...c.children];
    let contentBottom = r.top, contentTop = r.bottom;
    kids.forEach(k => { const kr = k.getBoundingClientRect();
      contentBottom = Math.max(contentBottom, kr.bottom); contentTop = Math.min(contentTop, kr.top); });
    return { i, title: t.replace(/\\s+/g,' ').slice(0,20), y: Math.round(r.y), h: Math.round(r.height),
             w: Math.round(r.width), contentH: Math.round(contentBottom - Math.max(contentTop, r.top)),
             slack: Math.round(r.bottom - contentBottom) };
  });
  return { cards: info, pageH: document.documentElement.scrollHeight,
           viewport: window.innerHeight };
})()`)
console.log(`页面总高 ${st.pageH}px / 视口 ${st.viewport}px，共 ${st.cards.length} 张卡片：`)
st.cards.forEach((c) => {
  const flag = c.slack > 24 ? `  ⚠ 底部空白 ${c.slack}px` : ''
  console.log(`   #${String(c.i).padStart(2)} y=${String(c.y).padStart(5)} h=${String(c.h).padStart(4)} w=${String(c.w).padStart(4)} 内容高=${String(c.contentH).padStart(4)} 「${c.title}」${flag}`)
})
await shot('diag-settings-layout.png')

// 两卡并排检查：主题强调色 与 背景外观 是否在同一行
const pair = await ev(`(() => {
  const cards = [...document.querySelectorAll('.card')];
  const a = cards.find(c => (c.innerText||'').includes('主题强调色'));
  const b = cards.find(c => (c.innerText||'').includes('背景外观'));
  if (!a || !b) return { missing: true };
  const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
  return { sameRow: Math.abs(ra.top - rb.top) < 30, aTop: Math.round(ra.top), bTop: Math.round(rb.top),
           aW: Math.round(ra.width), bW: Math.round(rb.width), aH: Math.round(ra.height), bH: Math.round(rb.height) };
})()`)
console.log(`  主题强调色与背景外观同一行: ${pair.sameRow}  (top ${pair.aTop} vs ${pair.bTop}, 宽 ${pair.aW} vs ${pair.bW}, 高 ${pair.aH} vs ${pair.bH})`)

/* ═══ ③ 学期管理弹窗 ═══ */
console.log('\n═══ ③ 学期管理弹窗 ═══')
await goto(`${WEB}/courses`)
await sleep(6500)
const opened = await clickText('button', '学期管理')
await sleep(2500)
const sem = await ev(`(() => {
  const modal = document.querySelector('.n-modal');
  if (!modal) return { noModal: true };
  const mw = modal.getBoundingClientRect();
  const grid = modal.querySelector('.sf-grid');
  const items = [...modal.querySelectorAll('.n-form-item')].map(fi => {
    const label = (fi.querySelector('.n-form-item-label')||{}).innerText || '';
    const inp = fi.querySelector('.n-input');
    const r = inp ? inp.getBoundingClientRect() : null;
    return { label: label.trim(), w: r ? Math.round(r.width) : null };
  });
  let cols = null;
  if (grid) cols = getComputedStyle(grid).gridTemplateColumns;
  // 检测标签与输入框是否重叠
  let overlap = 0;
  modal.querySelectorAll('.n-form-item').forEach(fi => {
    const lb = fi.querySelector('.n-form-item-label'), ip = fi.querySelector('.n-input');
    if (lb && ip) { const a = lb.getBoundingClientRect(), b = ip.getBoundingClientRect();
      if (a.right > b.left + 1) overlap++; }
  });
  return { modalW: Math.round(mw.width), cols, items, overlap,
           btnSave: !!([...modal.querySelectorAll('button')].find(b => (b.innerText||'').includes('保存修改'))),
           btnCreate: !!([...modal.querySelectorAll('button')].find(b => (b.innerText||'').includes('创建学期'))) };
})()`)
console.log(`弹窗宽 ${sem.modalW}px · 表单列 = [${sem.cols}]`)
console.log('表单项宽度：', JSON.stringify(sem.items))
console.log(`标签/输入框重叠: ${sem.overlap} 处  | 有「保存修改」按钮: ${sem.btnSave}`)
await shot('diag-semester-modal.png')

// 实测「保存修改」是否真的发出请求
let putCount = 0
await ev(`window.__putHit = 0; (() => {
  const of = window.fetch;
  window.fetch = function(...a) {
    const u = String(a[0] || '');
    const m = (a[1] && a[1].method) || 'GET';
    if (/\\/courses\\/semesters\\/\\d+/.test(u) && /PUT|PATCH/.test(m)) window.__putHit++;
    if (/\\/courses\\/semesters/.test(u) && /POST|PUT/.test(m)) window.__semHit = (window.__semHit||0)+1;
    return of.apply(this, a);
  };
})()`)
// 到输入框里改总周数
const typed = await ev(`(() => {
  const fi = [...document.querySelectorAll('.n-modal .n-form-item')].find(f => ((f.querySelector('.n-form-item-label')||{}).innerText||'').includes('总周数'));
  if (!fi) return 'no-field';
  const inp = fi.querySelector('input');
  if (!inp) return 'no-input';
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '22');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  return { w: Math.round(inp.getBoundingClientRect().width), val: inp.value };
})()`)
console.log('总周数输入框：', JSON.stringify(typed))
await sleep(800)
const saveOk = await ev(`(() => {
  const b = [...document.querySelectorAll('.n-modal button')].find(x => (x.innerText||'').includes('保存修改'));
  if (!b) return 'no-btn';
  b.click(); return 'clicked';
})()`)
await sleep(3500)
const after = await ev(`({ semHit: window.__semHit || 0, toast: (document.querySelector('.n-message')||{}).innerText || '' })`)
console.log(`点击「保存修改」= ${saveOk} → 学期接口请求数 ${after.semHit}  提示: ${after.toast.trim().slice(0,40)}`)
await shot('diag-semester-save.png')
await ev(`(() => { const b=[...document.querySelectorAll('.n-modal button')].find(x=>(x.innerText||'').includes('取消编辑')); if(b) b.click(); })()`)
await sleep(600)
await ev(`document.querySelector('.n-modal .n-base-close, .n-modal .n-card-header__close')?.click()`)
await sleep(1200)

/* ═══ ④ 空闲预测 + PDF 上传 ═══ */
console.log('\n═══ ④ 空闲预测推荐 / PDF 上传 ═══')
await goto(`${WEB}/classroom`)
await sleep(8000)
const pr = await ev(`(() => {
  const cards = [...document.querySelectorAll('.card')];
  const c = cards.find(x => (x.innerText||'').includes('空闲预测推荐'));
  if (!c) return { missing: true };
  const r = c.getBoundingClientRect();
  const rows = c.querySelectorAll('.pred-row, .p-row, [class*="pred"]');
  return { w: Math.round(r.width), h: Math.round(r.height),
           text: (c.innerText||'').replace(/\\s+/g,' ').slice(0, 200),
           childCount: c.children.length, rows: rows.length };
})()`)
console.log(`空闲预测卡片：${pr.missing ? '缺失' : `宽 ${pr.w} 高 ${pr.h} 子元素 ${pr.childCount}`}`)
console.log(`  文案：${pr.text || ''}`)
await shot('diag-prediction.png')

await goto(`${WEB}/courses`)
await sleep(6500)
const pdfUi = await ev(`(() => {
  const drop = document.querySelector('[class*="drop"], .drop-zone');
  const r = drop ? drop.getBoundingClientRect() : null;
  return { hasDrop: !!drop, h: r ? Math.round(r.height) : null,
           text: (document.body.innerText.match(/点击或拖拽[^\\n]*/)||[''])[0].slice(0,60) };
})()`)
console.log(`PDF 上传区：存在=${pdfUi.hasDrop} 高=${pdfUi.h}px`)
await shot('diag-pdf-upload.png')

console.log('\n── 未捕获异常 ──')
const uniq = [...new Set(exps)]
uniq.slice(0, 8).forEach((e) => console.log('  ⚠ ' + e))
if (!uniq.length) console.log('  （无）')

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}
console.log('\n截图：docs/diag-*.png')
