/**
 * 打包后的桌面应用（Electron）端到端验证 —— 只读检查，不修改用户数据
 *
 * 直接启动 release/win-unpacked/北极星个人战略终端.exe（带远程调试端口），
 * 在真实打包环境中核验 5 项修复。
 *
 * 用法： node scripts/verify-packaged-app.mjs
 */
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = 'F:\\deepseek harness  wenjian'
// 默认校验 release/win-unpacked；可用 APP_PATH 指向「已安装」的正式目录
const APP = process.env.APP_PATH
  || join(ROOT, 'polaris-desktop', 'release', 'win-unpacked', '北极星个人战略终端.exe')
const PORT = 9412
const OUT = join(ROOT, 'polaris-terminal', 'docs')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

if (!existsSync(APP)) { console.error('✗ 未找到打包应用：' + APP); process.exit(2) }
mkdirSync(OUT, { recursive: true })

// 单实例锁：若已有实例在运行，先结束（避免新窗口不启动）
const running = spawnSync('tasklist', ['/FI', 'IMAGENAME eq 北极星个人战略终端.exe', '/NH'], { encoding: 'utf8' })
if (/北极星/.test(running.stdout || '')) {
  console.log('检测到已有实例在运行，先结束以免单实例锁冲突…')
  spawnSync('taskkill', ['/IM', '北极星个人战略终端.exe', '/T', '/F'], { encoding: 'utf8' })
  await sleep(2500)
}

console.log('启动打包应用…')

// 重要：本机 DSH 运行环境可能设置了 ELECTRON_RUN_AS_NODE=1，
// 这会让 Electron 以「纯 Node」模式启动（表现为 bad option / 秒退、无窗口）。
// 这是测试环境问题，与打包产物无关，故在此显式清除。
const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE
delete env.ELECTRON_NO_ASAR
// 让 Chromium 不因窗口不可见而节流渲染/定时器（否则 evaluate 会超时）
env.ELECTRON_ENABLE_LOGGING = '0'

const child = spawn(APP, [
  `--remote-debugging-port=${PORT}`,
  '--disable-background-timer-throttling',
  '--disable-backgrounding-occluded-windows',
  '--disable-renderer-backgrounding',
  '--disable-features=CalculateNativeWinOcclusion',
], { stdio: 'ignore', env })

// 等待 Electron 的调试端口出现
let target = null
for (let i = 0; i < 100 && !target; i++) {
  await sleep(600)
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
    target = list.find((x) => x.type === 'page' && /127\.0\.0\.1/.test(x.url))
  } catch { /* 尚未就绪 */ }
}
if (!target) {
  console.error('✗ 未能连接到打包应用（调试端口无页面）')
  spawnSync('taskkill', ['/IM', '北极星个人战略终端.exe', '/T', '/F'], { encoding: 'utf8' })
  process.exit(2)
}
console.log('已连接：' + target.url)

const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej) })
let id = 0
const pending = new Map()
const exps = []
const loads = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params.exceptionDetails
    const url = d.url || d.stackTrace?.callFrames?.[0]?.url || ''
    if (!/^chrome-extension:/.test(url)) exps.push((d.exception?.description || d.text || '').split('\n')[0].slice(0, 160))
  }
  if (m.method === 'Page.loadEventFired') loads.push(1)
})
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej })
  ws.send(JSON.stringify({ id: i, method, params }))
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)) } }, 90000)
})
const ev = async (x) => {
  const r = await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval fail')
  return r.result?.value
}
async function goto(url) {
  loads.length = 0
  try { await send('Page.bringToFront') } catch { /* 忽略 */ }
  await send('Page.navigate', { url })
  const s = Date.now()
  while (Date.now() - s < 30000) { if (loads.length) return; await sleep(80) }
}
const shot = async (n) => {
  // 真实窗口在后台/被遮挡时 captureScreenshot 可能超时，截图失败不应中断验证
  try {
    const r = await send('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false })
    writeFileSync(join(OUT, n), Buffer.from(r.data, 'base64'))
  } catch (e) {
    console.log(`  (截图跳过 ${n}：${e.message})`)
  }
}

await send('Page.enable')
await send('Runtime.enable')

const results = []
const rec = (no, name, ok, detail) => {
  results.push({ no, name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} [${no}] ${name}${detail ? '  → ' + detail : ''}`)
}

await send('Page.enable')
await send('Runtime.enable')
// 窗口不在前台时 Chromium 会节流渲染与定时器，导致 evaluate 超时 → 主动置前
try { await send('Page.bringToFront') } catch { /* 忽略 */ }

const ORIGIN = new URL(target.url).origin
console.log('应用地址：' + ORIGIN + '\n')

/* 登录：优先使用已持久化的 token；若停在登录页则调用后端登录接口后写入 localStorage */
await goto(`${ORIGIN}/`)
await sleep(6000)
let path = await ev('location.pathname')
if (/\/login/.test(path)) {
  console.log('  当前停在登录页，执行登录…')
  const creds = [['admin', 'admin123']]
  let tok = null
  for (const [u, p] of creds) {
    const r = await fetch(`${ORIGIN}/api/v1/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p }),
    })
    if (r.ok) { const j = await r.json(); tok = j; console.log(`  已用 ${u} 登录成功`); break }
  }
  if (!tok) { console.error('✗ 登录失败，无法继续（可能不是 admin/admin123）'); }
  else {
    await ev(`localStorage.setItem('pl_token', ${JSON.stringify(tok.access_token)});
              localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(tok.user))});`)
    await goto(`${ORIGIN}/`)
    await sleep(8000)
    path = await ev('location.pathname')
    console.log('  登录后路径：' + path)
  }
}
const boot = await ev(`({
  text: document.body.innerText.trim().length,
  hash: location.pathname,
  hasSkeleton: !!document.querySelector('.boot,.skeleton'),
  errBar: !!document.querySelector('.ve-bar,.error-bar')
})`)
rec('P0', '应用启动未白屏', boot.text > 400, `正文 ${boot.text} 字 · 路径 ${boot.hash}`)
rec('P0b', '无全局错误提示条', !boot.errBar)
await shot('pkg-dashboard.png')

/* ① 空教室时间维度 */
await goto(`${ORIGIN}/classroom`)
await sleep(9000)
const cr = await ev(`({
  modes: [...document.querySelectorAll('.n-radio-button')].map(e => e.innerText.trim()),
  hours: document.querySelectorAll('.ctrl-hour').length,
  legend: (document.querySelector('.lg-note')||{}).innerText||'',
  sem: (document.querySelector('.sem-tip')||{}).innerText||'',
  cells: document.querySelectorAll('[class*="cell"]').length
})`)
rec('1.1', '三种时间模式齐全', cr.modes.length >= 3, JSON.stringify(cr.modes))
rec('1.2', '时段区间控件（开始~结束）', cr.hours >= 2, `${cr.hours} 个`)
rec('1.3', '学期/教学周提示已显示', /学期起始/.test(cr.sem) && /第\s*\d+\s*周/.test(cr.sem), cr.sem.trim().slice(0, 56))
rec('1.4', '教室占用格子已渲染', cr.cells > 0, `${cr.cells} 个`)
await shot('pkg-classroom.png')

/* ④ 新闻科技分类点击 */
await goto(`${ORIGIN}/news`)
await sleep(8000)
const n0 = await ev(`document.querySelectorAll('article.card').length`)
const clicked = await ev(`(() => {
  const b = [...document.querySelectorAll('.cat')].find(x => (x.innerText||'').includes('科技'));
  if (!b) return false; b.click(); return true;
})()`)
await sleep(5000)
const n1 = await ev(`({ url: location.href, cards: document.querySelectorAll('article.card').length })`)
rec('4.1', '科技分类可切换且有卡片', clicked && n1.cards > 0, `${n1.cards} 张`)
const opened = await ev(`(() => {
  const el = document.querySelector('article.card'); if (!el) return false;
  el.scrollIntoView({block:'center'}); el.click(); return true;
})()`)
await sleep(5000)
const n2 = await ev(`({
  modal: !!document.querySelector('.n-modal'),
  len: (((document.querySelector('.d-content')||{}).innerText)||'').trim().length,
  url: location.href
})`)
rec('4.2', '点击卡片打开详情弹窗', n2.modal && opened)
rec('4.3', '详情弹窗有正文', n2.len > 20, `${n2.len} 字`)
rec('4.4', '未发生同页跳转', n2.url.includes('/news'), n2.url)
await shot('pkg-news-detail.png')

/* ③ 知识库量化卡片（缩窄窗口模拟非全屏） */
await send('Emulation.setDeviceMetricsOverride', { width: 1200, height: 880, deviceScaleFactor: 1, mobile: false })
await goto(`${ORIGIN}/`)
await sleep(8000)
const kb = await ev(`(() => {
  const el = document.querySelector('.kb-body'); if (!el) return { missing: true };
  const card = el.closest('.card'); const cr = card.getBoundingClientRect();
  const kids = [...el.children].map(c => { const r = c.getBoundingClientRect();
    return { x:Math.round(r.x), y:Math.round(r.y), r:Math.round(r.right), b:Math.round(r.bottom) }; });
  const rows = {}; kids.forEach(k => { const key = Math.round(k.y/14); (rows[key] ||= []).push(k); });
  let overlap = 0;
  Object.values(rows).forEach(g => { for (let i=0;i<g.length;i++) for (let j=i+1;j<g.length;j++) {
    if (g[i].r > g[j].x+1 && g[j].r > g[i].x+1) overlap++; } });
  const cc = el.querySelector('canvas'); const cb = el.querySelector('.glow-chart');
  const cvr = cc ? cc.getBoundingClientRect() : null, cbr = cb ? cb.getBoundingClientRect() : null;
  return { overlap,
    leftRight: kids.filter(k => k.r > cr.right-1 || k.x < cr.left+1).length,
    bottom: kids.filter(k => k.b > cr.bottom-1).length,
    synced: (cvr && cbr) ? (Math.abs(cvr.width-cbr.width)<=2 && Math.abs(cvr.height-cbr.height)<=2) : true,
    cols: getComputedStyle(el).gridTemplateColumns };
})()`)
rec('3.1', '1200px 下无同行重叠', !kb.missing && kb.overlap === 0, kb.overlap === 0 ? `列=[${kb.cols}]` : `重叠 ${kb.overlap}`)
rec('3.2', '1200px 下无溢出', !kb.missing && kb.leftRight === 0 && kb.bottom === 0,
  `左右 ${kb.leftRight} / 底部 ${kb.bottom}`)
rec('3.3', '图表 canvas 与容器同步', !kb.missing && kb.synced)
await shot('pkg-dashboard-1200.png')
await send('Emulation.clearDeviceMetricsOverride')

/* ② 考研情报（只读：不切换院校，看当前院校两块卡片是否存在） */
await goto(`${ORIGIN}/kaoyan`)
await sleep(9000)
const ky = await ev(`({
  industry: !!document.body.innerText.includes('行业分布与就业率'),
  employer: !!document.body.innerText.includes('主要就业单位与岗位'),
  empCards: document.querySelectorAll('.emp-card').length,
  canvases: document.querySelectorAll('canvas').length,
  loading: document.body.innerText.includes('正在抓取目标院校公开数据'),
  miss: document.body.innerText.includes('暂未获取到该校情报')
})`)
rec('2.1', '「行业分布与就业率」区块存在', ky.industry, ky.miss ? '（该校情报不可用提示）' : '')
rec('2.2', '「主要就业单位与岗位」区块存在', ky.employer)
rec('2.3', '就业单位卡片有内容', ky.empCards > 0, `${ky.empCards} 张`)
rec('2.4', '行业分布图已渲染', ky.canvases > 0, `canvas ${ky.canvases}`)
rec('2.5', '不再卡在「正在抓取」', !ky.loading)
await shot('pkg-kaoyan.png')

/* ⑤ 背景外观面板 */
await goto(`${ORIGIN}/settings`)
await sleep(8000)
const st = await ev(`({
  panel: document.body.innerText.includes('个性化外观'),
  presets: document.querySelectorAll('.bg-preset').length,
  sliders: document.querySelectorAll('.bg-slider').length,
  colors: document.querySelectorAll('.bg-color-chip').length,
  preview: !!document.querySelector('.bvp'),
  wall: document.body.innerText.includes('选择壁纸'),
  reset: document.body.innerText.includes('恢复默认'),
  accent: document.querySelectorAll('.accent-btn').length
})`)
rec('5.1', '个性化外观面板存在（强调色+背景已合并）', st.panel && st.accent >= 4, `${st.accent} 个强调色`)
rec('5.2', '光晕配色预设', st.presets >= 4, `${st.presets} 个`)
rec('5.3', '强度/纹理/圆角滑块', st.sliders >= 3, `${st.sliders} 个`)
rec('5.4', '底色选择', st.colors >= 4, `${st.colors} 个快捷色`)
rec('5.5', '自定义壁纸入口', st.wall)
rec('5.6', '实时预览 + 恢复默认', st.preview && st.reset)
await shot('pkg-settings.png')

/* 异常汇总 */
console.log('\n── 未捕获异常 ──')
const uniq = [...new Set(exps)]
uniq.slice(0, 8).forEach((e) => console.log('  ⚠ ' + e))
if (!uniq.length) console.log('  （无）')
rec('6.1', '打包应用无未捕获异常', uniq.length === 0, uniq.length ? `${uniq.length} 条` : '无')

/* 结束应用 */
ws.close()
spawnSync('taskkill', ['/IM', '北极星个人战略终端.exe', '/T', '/F'], { encoding: 'utf8' })
console.log('\n已关闭打包应用。')

const bad = results.filter((r) => !r.ok)
console.log('═'.repeat(60))
console.log(`打包应用端到端：共 ${results.length} 项，通过 ${results.length - bad.length}，失败 ${bad.length}`)
if (bad.length) {
  console.log('\n失败项：')
  bad.forEach((r) => console.log(`  ✗ [${r.no}] ${r.name}${r.detail ? ' → ' + r.detail : ''}`))
}
console.log('截图：polaris-terminal/docs/pkg-*.png')
process.exit(bad.length ? 1 : 0)
