/**
 * 第二轮 4 项修复的端到端验证
 *
 * ① 系统设置：主题强调色与背景外观合并为一张卡、同侧栏、无明显空白
 * ② 考研情报：域名注册表覆盖 + 随机院校也能返回分数线/就业数据曲线
 * ③ 学期管理：总周数输入框宽度正常、标签不重叠、保存修改可用
 * ④ 空闲预测：不再空白（空状态 + 按课表推算的无课教室）；PDF 失败信息完整可读
 *
 * 用法： node scripts/verify-round2.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:5200'
const PORT = 9428
const OUT = 'docs'
const EDGE = ['C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'].find((p) => existsSync(p))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const results = []
const rec = (no, name, ok, detail) => {
  results.push({ no, name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} [${no}] ${name}${detail ? '  → ' + detail : ''}`)
}

const lg = await fetch(`${API}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' }),
})
const auth = await lg.json()
mkdirSync(OUT, { recursive: true })
const profile = join(tmpdir(), `edge-r2-${Date.now()}`)
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

await send('Page.enable'); await send('Runtime.enable')
await goto(`${WEB}/login`)
await ev(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
          localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

/* ══════ ① 系统设置合并布局 ══════ */
console.log('── ① 系统设置：合并 + 紧凑 ──')
await goto(`${WEB}/settings`); await sleep(6500)
const s1 = await ev(`(() => {
  const cards = [...document.querySelectorAll('.card')];
  const p = cards.find(c => (c.innerText||'').includes('个性化外观'));
  if (!p) return { missing: true };
  const pr = p.getBoundingClientRect();
  // 卡片内是否有明显空白：控制栏与预览栏高度差
  const body = p.querySelector('.p-body');
  const ctrl = p.querySelector('.p-ctrl'), prev = p.querySelector('.p-preview');
  const cr = ctrl?.getBoundingClientRect(), vr = prev?.getBoundingClientRect();
  return {
    hasAccent: (p.innerText||'').includes('主题强调色'),
    hasAppearance: (p.innerText||'').includes('光晕配色'),
    hasPreview: !!p.querySelector('.bvp'),
    cardW: Math.round(pr.width), cardH: Math.round(pr.height),
    ctrlH: cr ? Math.round(cr.height) : null, prevH: vr ? Math.round(vr.height) : null,
    sameSide: cr && vr ? Math.abs(cr.top - vr.top) < 20 : false,
    accentBtns: p.querySelectorAll('.accent-btn').length,
    presets: p.querySelectorAll('.bg-preset').length,
    sliders: p.querySelectorAll('.bg-slider').length,
    cardCount: cards.length,
  };
})()`)
rec('1.1', '强调色与背景外观合并到同一张卡', !s1.missing && s1.hasAccent && s1.hasAppearance)
rec('1.2', '预览栏与控制在同侧并排（不再上下分离）', s1.sameSide, `控制高 ${s1.ctrlH} / 预览高 ${s1.prevH}`)
rec('1.3', '卡片占满整行宽度', s1.cardW > 1200, `${s1.cardW}px`)
rec('1.4', '控件齐全（强调色/预设/滑杆）',
  s1.accentBtns >= 4 && s1.presets >= 4 && s1.sliders >= 3,
  `${s1.accentBtns} 色 / ${s1.presets} 预设 / ${s1.sliders} 滑杆`)

// 纵向留白：预览区应填满右侧，其底部与左侧控制栏底部不应差太多
const gap = s1.ctrlH && s1.prevH ? Math.abs(s1.ctrlH - s1.prevH) : 999
rec('1.5', '右侧预览区填满（与左侧高度差 ≤60px）', gap <= 60, `高度差 ${gap}px`)

// 全页高度应下降（更紧凑）
const pageH = await ev(`document.documentElement.scrollHeight`)
rec('1.6', '页面总高较此前下降（更紧凑）', pageH < 1900, `当前 ${pageH}px（此前 1957px）`)
await shot('r2-settings.png')

/* ══════ ③ 学期管理弹窗 ══════ */
console.log('\n── ③ 学期管理弹窗 ──')
await goto(`${WEB}/courses`); await sleep(6500)
await clickText('button', '学期管理'); await sleep(2500)
const s3 = await ev(`(() => {
  const modal = document.querySelector('.n-modal');
  if (!modal) return { noModal: true };
  const items = [...modal.querySelectorAll('.sf-item')].map(fi => {
    const lb = fi.querySelector('.sf-label'), inp = fi.querySelector('.n-input, .n-input-number');
    const lr = lb?.getBoundingClientRect(), ir = inp?.getBoundingClientRect();
    return { label: (lb?.innerText||'').trim(), w: ir ? Math.round(ir.width) : null,
             overlap: (lr && ir) ? lr.bottom > ir.top + 2 : false };
  });
  return { items, overlaps: items.filter(x => x.overlap).length,
           hasSave: !!([...modal.querySelectorAll('button')].find(b => (b.innerText||'').includes('保存修改'))),
           hasCreate: !!([...modal.querySelectorAll('button')].find(b => (b.innerText||'').includes('创建学期'))),
           cols: getComputedStyle(modal.querySelector('.sf-grid')).gridTemplateColumns };
})()`)
console.log('   表单项：', JSON.stringify(s3.items))
const weeks = s3.items?.find((x) => x.label?.includes('总周数'))
rec('3.1', '总周数输入框宽度正常（≥70px）', weeks && weeks.w >= 70, `${weeks?.w}px（修复前 23px）`)
rec('3.2', '标签与输入框无重叠', s3.overlaps === 0, `${s3.overlaps} 处`)
rec('3.3', '「创建/保存」按钮可见', s3.hasCreate || s3.hasSave)
await shot('r2-semester-modal.png')

// 实测保存：先编辑现有学期再保存
await clickText('.n-modal button', '编辑'); await sleep(1500)
await ev(`window.__semHit = 0; (() => { const of = window.fetch;
  window.fetch = function(...a){ const u=String(a[0]||''); const m=(a[1]&&a[1].method)||'GET';
    if (/\\/courses\\/semesters/.test(u) && /PUT|PATCH|POST/.test(m)) window.__semHit++;
    return of.apply(this,a); }; })()`)
const typed = await ev(`(() => {
  const fi = [...document.querySelectorAll('.n-modal .sf-item')].find(f => ((f.querySelector('.sf-label')||{}).innerText||'').includes('总周数'));
  if (!fi) return 'no-field';
  const inp = fi.querySelector('input');
  if (!inp) return 'no-input';
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '21');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  return { w: Math.round(inp.getBoundingClientRect().width), val: inp.value };
})()`)
console.log('   写入总周数：', JSON.stringify(typed))
await sleep(700)
const clicked = await ev(`(() => {
  const b = [...document.querySelectorAll('.n-modal button')].find(x => (x.innerText||'').includes('保存修改'));
  if (!b) return 'no-btn'; b.click(); return 'ok';
})()`)
await sleep(3500)
const after = await ev(`({ hit: window.__semHit||0, toast: (document.querySelector('.n-message')||{}).innerText||'' })`)
rec('3.4', '点击「保存修改」真实发出请求', clicked === 'ok' && after.hit > 0,
  `按钮=${clicked} 请求数=${after.hit} 提示=${after.toast.trim().slice(0,20)}`)
await shot('r2-semester-saved.png')
await ev(`document.querySelector('.n-modal .n-base-close')?.click()`)
await sleep(1000)

/* ══════ ④ 空闲预测 + PDF 错误可读性 ══════ */
console.log('\n── ④ 空闲预测 / PDF ──')
await goto(`${WEB}/classroom`); await sleep(8000)
const s4 = await ev(`(() => {
  const c = [...document.querySelectorAll('.card')].find(x => (x.innerText||'').includes('空闲预测推荐'));
  if (!c) return { missing: true };
  const r = c.getBoundingClientRect();
  const empty = c.querySelector('.pred-empty');
  const freeList = c.querySelectorAll('.pf-item').length;
  const rows = c.querySelectorAll('.p-row').length;
  const ops = c.querySelectorAll('.pe-ops button').length;
  // 内容实际占用高度
  let bottom = r.top;
  [...c.children].forEach(k => { bottom = Math.max(bottom, k.getBoundingClientRect().bottom) });
  return { h: Math.round(r.height), contentH: Math.round(bottom - r.top),
           slack: Math.round(r.bottom - bottom),
           hasEmpty: !!empty, emptyTitle: (empty?.querySelector('.pe-title')||{}).innerText||'',
           freeList, rows, ops,
           text: (c.innerText||'').replace(/\\s+/g,' ').slice(0,150) };
})()`)
rec('4.1', '空闲预测卡片存在', !s4.missing)
rec('4.2', '无快照时显示空状态说明（不再整块空白）', s4.hasEmpty, s4.emptyTitle?.slice(0, 40))
rec('4.3', '给出按课表推算的无课教室', s4.freeList > 0, `${s4.freeList} 间`)
rec('4.4', '提供可操作入口', s4.ops >= 2, `${s4.ops} 个按钮`)
rec('4.5', '卡片底部无明显留白（≤40px）', s4.slack <= 40, `留白 ${s4.slack}px（修复前 807px 空白）`)
await shot('r2-prediction.png')

// PDF 失败信息
await goto(`${WEB}/courses?view=pdf`); await sleep(7500)
const s5 = await ev(`(() => {
  const err = document.querySelector('.up-error');
  const sug = document.querySelectorAll('.up-sug li').length;
  const ops = document.querySelectorAll('.up-ops button').length;
  const mode = (document.body.innerText.match(/模式\\s*(\\S+)/)||[])[1] || '';
  return { hasErr: !!err,
           errFull: (err?.innerText||'').replace(/\\s+/g,' ').trim(),
           errH: err ? Math.round(err.getBoundingClientRect().height) : 0,
           sug, ops, mode,
           rawMode: /image_only|grid|list|vision/.test(document.body.innerText) };
})()`)
rec('4.6', 'PDF 解析失败信息完整展示', s5.hasErr && s5.errFull.length > 20,
  `${s5.errH}px 高 · ${s5.errFull.slice(0, 56)}`)
rec('4.7', '解析模式显示为中文（不再裸露内部标识）', !s5.rawMode, `mode=${s5.mode}`)
rec('4.8', '给出多条处理建议 + 补救入口', s5.sug >= 2 && s5.ops >= 2,
  `${s5.sug} 条建议 / ${s5.ops} 个入口`)
await shot('r2-pdf-error.png')

/* ══════ ② 考研情报（后端能力） ══════ */
console.log('\n── ② 考研情报：随机院校 ──')
const H = { Authorization: `Bearer ${auth.access_token}`, 'Content-Type': 'application/json' }
const orig = await (await fetch(`${API}/api/v1/kaoyan/target`, { headers: H })).json()
const schools = ['西安电子科技大学', '郑州大学', '昆明理工大学', '哈尔滨工程大学', '某某师范大学']
let okCount = 0
for (const sc of schools) {
  await fetch(`${API}/api/v1/kaoyan/target`, { method: 'PUT', headers: H,
    body: JSON.stringify({ school: sc, major: '计算机科学与技术', degree_type: '学硕' }) })
  const t0 = Date.now()
  const d = await (await fetch(`${API}/api/v1/kaoyan/intel`, { headers: H })).json()
  const ms = Date.now() - t0
  const emp = d.employment || {}
  const lines = d.score_lines || []
  const ok = lines.length > 0 && (emp.industry || []).length > 0
  if (ok) okCount++
  console.log(`   ${ok ? '✓' : '✗'} ${sc.padEnd(10)} 分数线 ${lines.length} 条 · 行业 ${(emp.industry||[]).length} 项 · ${ms}ms`)
}
rec('2.1', `随机院校均能返回分数线与就业数据（${okCount}/${schools.length}）`, okCount === schools.length)
await fetch(`${API}/api/v1/kaoyan/target`, { method: 'PUT', headers: H,
  body: JSON.stringify({ school: orig.school, major: orig.major, degree_type: orig.degree_type || '学硕' }) })
console.log(`   ↺ 已恢复目标院校：${orig.school}`)

// 曲线图渲染
await goto(`${WEB}/kaoyan`); await sleep(8000)
const ky = await ev(`({
  industry: !!document.body.innerText.includes('行业分布与就业率'),
  employer: !!document.body.innerText.includes('主要就业单位与岗位'),
  canvases: document.querySelectorAll('canvas').length,
  empCards: document.querySelectorAll('.emp-card').length
})`)
rec('2.2', '考研页图表与就业卡片渲染', ky.canvases >= 2 && ky.empCards > 0,
  `canvas ${ky.canvases} / 单位卡 ${ky.empCards}`)
await shot('r2-kaoyan.png')

console.log('\n── 未捕获异常 ──')
const uniq = [...new Set(exps)]
uniq.slice(0, 8).forEach((e) => console.log('  ⚠ ' + e))
if (!uniq.length) console.log('  （无）')
rec('5.1', '无未捕获运行时异常', uniq.length === 0, uniq.length ? `${uniq.length} 条` : '无')

ws.close(); child.kill()
try { rmSync(profile, { recursive: true, force: true }) } catch {}

const bad = results.filter((r) => !r.ok)
console.log('\n' + '═'.repeat(60))
console.log(`第二轮验证：共 ${results.length} 项，通过 ${results.length - bad.length}，失败 ${bad.length}`)
if (bad.length) { console.log('\n失败项：'); bad.forEach((r) => console.log(`  ✗ [${r.no}] ${r.name}${r.detail ? ' → ' + r.detail : ''}`)) }
process.exit(bad.length ? 1 : 0)
