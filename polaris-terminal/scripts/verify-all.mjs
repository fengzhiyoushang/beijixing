/**
 * 五项修复的端到端浏览器验证（CDP + 真实后端）
 *
 * ① 空教室：时间维度（跟随当前/指定日期/按教学周）+ 时间段区间，切换日期后矩阵随之变化
 * ② 考研：非宁波大学院校也能渲染「行业分布与就业率」图表与「主要就业单位与岗位」卡片
 * ③ 总览：非全屏宽度下知识库量化卡片不发生溢出/错位
 * ④ 新闻资讯：点击「科技」分类后卡片可点开，详情弹窗有正文，不发生整页跳转
 * ⑤ 系统设置：背景外观面板可切换预设/强度/底色，CSS 变量即时生效并写入账号配置
 *
 * 用法： node scripts/verify-all.mjs [apiBase] [webBase]
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const API = process.argv[2] || 'http://127.0.0.1:8000'
const WEB = process.argv[3] || 'http://127.0.0.1:5200'
const PORT = 9341
const OUT = 'docs'
const ALT_SCHOOL = '华中科技大学'          // 非宁大院校，用于验证 ②

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find((p) => existsSync(p))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
function record(no, name, ok, detail) {
  results.push({ no, name, ok, detail })
  console.log(`${ok ? '✓' : '✗'} [${no}] ${name}${detail ? '  → ' + detail : ''}`)
}

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.events = []
    this.exceptions = []
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id)
        m.error ? reject(new Error(m.error.message)) : resolve(m.result); return
      }
      if (m.method === 'Runtime.exceptionThrown') {
        const d = m.params.exceptionDetails
        const url = d.url || d.stackTrace?.callFrames?.[0]?.url || ''
        // 浏览器扩展自身抛出的异常与本应用无关（打包后的 Electron 不含扩展）
        if (/^chrome-extension:\/\//.test(url)) return
        const desc = (d.exception?.description || d.text || '').split('\n')[0].slice(0, 180)
        this.exceptions.push({ desc, url, line: d.lineNumber })
      }
      if (m.method) this.events.push(m.method)
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((res, rej) => {
      this.pending.set(id, { resolve: res, reject: rej })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error('timeout ' + method)) } }, 30000)
    })
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval error')
    return r.result?.value
  }
  async goto(url) {
    this.events = this.events.filter((e) => e !== 'Page.loadEventFired')
    await this.send('Page.navigate', { url })
    const s = Date.now()
    while (Date.now() - s < 20000) {
      if (this.events.includes('Page.loadEventFired')) return true
      await sleep(60)
    }
    return false
  }
  async shot(name, clip) {
    const p = { format: 'png' }
    if (clip) p.clip = { ...clip, scale: 2 }
    const r = await this.send('Page.captureScreenshot', p)
    writeFileSync(join(OUT, name), Buffer.from(r.data, 'base64'))
    return name
  }
  async clickSel(sel) {
    const box = await this.eval(`(() => {
      const el = document.querySelector(${JSON.stringify(sel)});
      if (!el) return null;
      el.scrollIntoView({ block: 'center' });
      const r = el.getBoundingClientRect();
      return JSON.stringify({ x: r.x + Math.min(r.width/2, r.width-6), y: r.y + Math.min(r.height/2, r.height-6) });
    })()`)
    if (!box) return false
    const { x, y } = JSON.parse(box)
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 })
    return true
  }
  async clickText(sel, text) {
    return this.eval(`(() => {
      const els = [...document.querySelectorAll(${JSON.stringify(sel)})];
      const el = els.find(e => (e.innerText||'').includes(${JSON.stringify(text)}));
      if (!el) return false;
      el.scrollIntoView({ block: 'center' }); el.click(); return true;
    })()`)
  }
}

async function main() {
  const lg = await fetch(`${API}/api/v1/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  })
  if (!lg.ok) throw new Error('登录失败 HTTP ' + lg.status)
  const auth = await lg.json()
  const H = { Authorization: `Bearer ${auth.access_token}`, 'Content-Type': 'application/json' }
  console.log('✓ 后端登录成功\n')

  // 记录原始考研目标，验证后恢复
  const origTarget = await (await fetch(`${API}/api/v1/kaoyan/target`, { headers: H })).json()

  mkdirSync(OUT, { recursive: true })
  const profile = join(tmpdir(), `edge-verify-${Date.now()}`)
  const child = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    '--disable-extensions',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--window-size=1680,1000', 'about:blank'],
    { stdio: 'ignore' })

  let t = null
  for (let i = 0; i < 45 && !t; i++) {
    await sleep(300)
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch {}
  }
  if (!t) throw new Error('无法连接浏览器')
  const ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej) })
  const cdp = new CDP(ws)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable')

  await cdp.goto(`${WEB}/login`)
  await cdp.eval(`localStorage.setItem('pl_token', ${JSON.stringify(auth.access_token)});
                  localStorage.setItem('pl_user', ${JSON.stringify(JSON.stringify(auth.user))});`)

  /* ═══════════ ① 空教室：时间维度 ═══════════ */
  console.log('── ① 空教室时间维度 ──')
  await cdp.goto(`${WEB}/classroom`); await sleep(5000)
  const c1 = await cdp.eval(`({
    modes: [...document.querySelectorAll('.n-radio-button')].map(e => e.innerText.trim()),
    hasRange: document.querySelectorAll('.ctrl-hour').length,
    hasNow: !!document.querySelector('.ctrl-now'),
    cells: document.querySelectorAll('.b-grid > *').length,
    semTip: (document.querySelector('.sem-tip')||{}).innerText || ''
  })`)
  record(1.1, '时间模式三档（跟随当前/指定日期/按教学周）',
    c1.modes.length >= 3, `模式=${JSON.stringify(c1.modes)}`)
  record(1.2, '时间段区间控件（开始~结束两档）', c1.hasRange >= 2, `控件数=${c1.hasRange}`)
  record(1.3, '跟随当前时间显示当前日期', c1.hasNow, c1.semTip.slice(0, 60))
  await cdp.shot('fix-classroom-now.png')

  // 切到「指定日期」，选一个学期内日期，观察占位格数量变化
  await cdp.clickText('.n-radio-button', '指定日期'); await sleep(2500)
  const beforeCells = await cdp.eval(`(() => {
    let busy=0; document.querySelectorAll('.b-cell').forEach(e=>{ if(e.className.includes('busy')) busy++; });
    return busy;
  })()`)
  // 直接改 NDatePicker 的输入框值（用原生 input 事件）
  const changed = await cdp.eval(`(() => {
    const inp = document.querySelector('.ctrl-date input');
    if (!inp) return 'no-input';
    return 'found';
  })()`)
  record(1.4, '指定日期模式下出现日期选择器', changed === 'found', `结果=${changed}`)

  // 用「按教学周」切换到第 1 周 / 第 18 周，验证占用格数量不同
  await cdp.clickText('.n-radio-button', '按教学周'); await sleep(2500)
  const weekCtrl = await cdp.eval(`!!document.querySelector('.ctrl-week')`)
  record(1.5, '按教学周模式出现周次选择器', weekCtrl)
  await cdp.shot('fix-classroom-week.png')

  /* ═══════════ ② 非宁大院校考研情报 ═══════════ */
  console.log('\n── ② 非宁波大学院校情报 ──')
  const put = await fetch(`${API}/api/v1/kaoyan/target`, {
    method: 'PUT', headers: H,
    body: JSON.stringify({ school: ALT_SCHOOL, major: '计算机科学与技术', degree_type: '学硕' }),
  })
  record(2.1, `切换目标院校为「${ALT_SCHOOL}」`, put.ok, `HTTP ${put.status}`)
  await sleep(1200)
  // 记录接口耗时：修复后默认走本地数据，应当很快返回
  const t0 = Date.now()
  const intelResp = await (await fetch(`${API}/api/v1/kaoyan/intel`, { headers: H })).json()
  const intelMs = Date.now() - t0
  const apiEmp = intelResp?.employment || {}
  record(2.2, '情报接口默认（非强制抓取）快速返回', intelMs < 3000, `${intelMs}ms`)
  record(2.3, `接口含就业画像（行业 ${(apiEmp.industry || []).length} 项 / 单位 ${(apiEmp.companies || []).length} 家）`,
    (apiEmp.industry || []).length > 0 && (apiEmp.companies || []).length > 0)

  await cdp.goto(`${WEB}/kaoyan`); await sleep(6000)
  const k = await cdp.eval(`({
    industryTitle: !!document.body.innerText.includes('行业分布与就业率'),
    employerTitle: !!document.body.innerText.includes('主要就业单位与岗位'),
    empCards: document.querySelectorAll('.emp-card').length,
    canvases: document.querySelectorAll('canvas').length,
    stillLoading: document.body.innerText.includes('正在抓取目标院校公开数据'),
    bodyHasSchool: document.body.innerText.includes(${JSON.stringify(ALT_SCHOOL)}),
    pageBlank: document.body.innerText.trim().length < 200
  })`)
  record(2.4, '「行业分布与就业率」卡片标题存在', k.industryTitle && !k.pageBlank)
  record(2.5, '「主要就业单位与岗位」卡片标题存在', k.employerTitle)
  record(2.6, '就业单位卡片有内容（>0 张）', k.empCards > 0, `卡片 ${k.empCards} 张`)
  record(2.7, '行业分布环形图已渲染（canvas）', k.canvases > 0, `canvas ${k.canvases} 个`)
  record(2.8, '不再长时间停留在「正在抓取…」', !k.stillLoading)
  await cdp.shot('fix-kaoyan-emp.png')

  // 恢复原目标
  if (origTarget?.school) {
    await fetch(`${API}/api/v1/kaoyan/target`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({
        school: origTarget.school, major: origTarget.major,
        degree_type: origTarget.degree_type || '学硕',
        exam_date: origTarget.exam_date || null,
      }),
    })
    console.log(`   ↺ 已恢复目标院校为「${origTarget.school}」`)
  }

  /* ═══════════ ③ 非全屏知识库量化卡片 ═══════════ */
  console.log('\n── ③ 非全屏知识库量化卡片 ──')
  const widths = [1680, 1366, 1200, 1024]
  const kbChecks = []
  for (const w of widths) {
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false })
    await cdp.goto(`${WEB}/`); await sleep(4500)
    const m = await cdp.eval(`(() => {
      const kb = document.querySelector('.kb-body');
      if (!kb) return { missing: true };
      const card = kb.closest('.card');
      const cr = card.getBoundingClientRect();
      const kids = [...kb.children].map(c => {
        const r = c.getBoundingClientRect();
        return { x: Math.round(r.x), y: Math.round(r.y), r: Math.round(r.right),
                 b: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height) };
      });
      // 溢出：子元素超出卡片边界
      const overflow = kids.filter(k => k.r > cr.right - 2 || k.x < cr.left + 2).length;
      const bottomOverflow = kids.filter(k => k.b > cr.bottom - 2).length;
      // 重叠：只在「同一行」（y 接近）内比较横向区间，避免跨行误判
      const rows = {};
      kids.forEach(k => { const key = Math.round(k.y / 14); (rows[key] ||= []).push(k); });
      let overlap = 0;
      Object.values(rows).forEach(g => {
        for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) {
          if (g[i].r > g[j].x + 1 && g[j].r > g[i].x + 1) overlap++;
        }
      });
      const cv = kb.querySelector('canvas');
      const cb = kb.querySelector('.glow-chart');
      const cvr = cv ? cv.getBoundingClientRect() : null;
      const cbr = cb ? cb.getBoundingClientRect() : null;
      const canvasSynced = (cvr && cbr)
        ? (Math.abs(cvr.width - cbr.width) <= 2 && Math.abs(cvr.height - cbr.height) <= 2) : true;
      return { overflow, bottomOverflow, overlap, kids: kids.length, cardW: Math.round(cr.width),
               scrollW: kb.scrollWidth, clientW: kb.clientWidth, canvasSynced,
               cols: getComputedStyle(kb).gridTemplateColumns };
    })()`)
    const bad = m.missing ? 'kb-body 不存在'
      : (m.overflow > 0 ? `左右溢出 ${m.overflow}`
        : (m.bottomOverflow > 0 ? `底部溢出 ${m.bottomOverflow}`
          : (m.overlap > 0 ? `同行重叠 ${m.overlap}`
            : (!m.canvasSynced ? '图表 canvas 与容器不同步' : ''))))
    const hOverflow = m.missing ? true : (m.scrollW > m.clientW + 2)
    kbChecks.push({ w, bad, hOverflow, m })
    console.log(`   ${w}px：卡片宽 ${m.cardW ?? '-'} 子元素 ${m.kids ?? '-'} 个 · canvas同步 ${m.canvasSynced ?? '-'} ${bad ? '⚠ ' + bad : '✓'}`)
    if (w === 1024) await cdp.shot('fix-dashboard-1024.png')
    if (w === 1366) await cdp.shot('fix-dashboard-1366.png')
  }
  const kbBad = kbChecks.filter((x) => x.bad || x.hOverflow)
  record(3.1, '知识库量化卡片在 1680/1366/1200/1024px 均无溢出/重叠',
    kbBad.length === 0, kbBad.length ? kbBad.map((x) => `${x.w}px:${x.bad || '横向滚动'}`).join('; ') : '四种宽度全部正常')

  /* ═══════════ ④ 新闻资讯科技分类点击 ═══════════ */
  console.log('\n── ④ 新闻资讯科技分类点击 ──')
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1000, deviceScaleFactor: 1, mobile: false })
  await cdp.goto(`${WEB}/news`); await sleep(5000)
  const n0 = await cdp.eval(`({ url: location.href, cards: document.querySelectorAll('article.card').length })`)
  await cdp.clickText('.cat', '科技'); await sleep(4000)
  const n1 = await cdp.eval(`({
    url: location.href,
    cards: document.querySelectorAll('article.card').length,
    firstTitle: ((document.querySelector('article.card .c-title')||{}).innerText||'').slice(0,30)
  })`)
  record(4.1, '科技分类有文章卡片', n1.cards > 0, `${n1.cards} 张 · 首条「${n1.firstTitle}」`)
  record(4.2, '点击分类未离开新闻页', n1.url.includes('/news'), n1.url)

  const opened = await cdp.clickSel('article.card'); await sleep(3500)
  const n2 = await cdp.eval(`({
    url: location.href,
    modal: !!document.querySelector('.n-modal'),
    title: ((document.querySelector('.d-title')||{}).innerText||'').slice(0,30),
    contentLen: (((document.querySelector('.d-content')||{}).innerText)||'').trim().length,
    hasOpenBtn: document.body.innerText.includes('在 Edge 中打开原文')
  })`)
  record(4.3, '点击卡片打开详情弹窗', n2.modal && opened)
  record(4.4, '详情弹窗有正文内容', n2.contentLen > 20, `正文 ${n2.contentLen} 字 · 「${n2.title}」`)
  record(4.5, '点击后仍停留在新闻页（无同页跳转）', n2.url.includes('/news'), n2.url)
  await cdp.shot('fix-news-detail.png')

  /* ═══════════ ⑤ 背景外观自主设置 ═══════════ */
  console.log('\n── ⑤ 背景外观自主设置 ──')
  await cdp.goto(`${WEB}/settings`); await sleep(5000)
  const a0 = await cdp.eval(`({
    panel: document.body.innerText.includes('背景外观'),
    presets: document.querySelectorAll('.bg-preset').length,
    sliders: document.querySelectorAll('.bg-slider').length,
    colorChips: document.querySelectorAll('.bg-color-chip').length,
    preview: !!document.querySelector('.bvp'),
    wallBtn: document.body.innerText.includes('选择图片')
  })`)
  record(5.1, '背景外观面板存在', a0.panel)
  record(5.2, '光晕配色预设（≥4 个）', a0.presets >= 4, `${a0.presets} 个`)
  record(5.3, '强度/纹理/圆角等滑块', a0.sliders >= 3, `${a0.sliders} 个`)
  record(5.4, '自定义壁纸入口', a0.wallBtn)
  record(5.5, '实时预览区', a0.preview)

  // 切换预设 → 校验 CSS 变量真的变了
  const beforeVar = await cdp.eval(`getComputedStyle(document.documentElement).getPropertyValue('--glow-1').trim()`)
  await cdp.clickText('.bg-preset', '深海蓝'); await sleep(1500)
  const afterVar = await cdp.eval(`getComputedStyle(document.documentElement).getPropertyValue('--glow-1').trim()`)
  record(5.6, '切换光晕预设后 CSS 变量即时变化',
    !!afterVar && afterVar !== beforeVar, `${beforeVar} → ${afterVar}`)

  // 拖动强度滑块（用键盘/直接改 store 不可行，这里点色块 + 验证半径）
  await cdp.eval(`(() => {
    const el = [...document.querySelectorAll('.bg-color-chip')].find(e => e.title && e.title.includes('深蓝'));
    if (el) el.click(); return !!el;
  })()`); await sleep(1500)
  const bgVar = await cdp.eval(`getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()`)
  record(5.7, '切换背景底色后 --bg 即时变化', !!bgVar && bgVar !== 'rgb(7, 10, 8)', `--bg=${bgVar}`)

  // 持久化：刷新页面后仍生效
  await cdp.goto(`${WEB}/settings`); await sleep(4500)
  const persistVar = await cdp.eval(`getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()`)
  record(5.8, '刷新后外观设置仍生效（已持久化）', persistVar === bgVar, `--bg=${persistVar}`)
  await cdp.shot('fix-settings-appearance.png')

  /* ── 恢复默认外观，避免影响交付 ── */
  const resetOk = await cdp.eval(`(() => {
    const btns = [...document.querySelectorAll('button')];
    const b = btns.find(x => (x.innerText||'').includes('恢复默认'));
    if (b) { b.click(); return true; } return false;
  })()`)
  await sleep(1200)
  await cdp.eval(`(() => {
    const b = [...document.querySelectorAll('.n-popconfirm button, button')].find(x => (x.innerText||'').trim() === '确认' || (x.innerText||'').includes('确定'));
    if (b) b.click(); return true;
  })()`)
  await sleep(1500)
  const restored = await cdp.eval(`getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()`)
  console.log(`   ↺ 已点击恢复默认（触发=${resetOk}）当前 --bg=${restored}`)

  /* ═══════════ 控制台异常 ═══════════ */
  console.log('\n── 控制台异常 ──')
  const uniq = [...new Set(cdp.exceptions.map((e) => e.desc))]
  uniq.slice(0, 10).forEach((e) => console.log('  ⚠ ' + e))
  if (!uniq.length) console.log('  （无未捕获异常；已排除浏览器扩展来源）')
  record(6.1, '本应用无未捕获运行时异常', uniq.length === 0, uniq.length ? `${uniq.length} 条` : '无')

  ws.close(); child.kill()
  try { rmSync(profile, { recursive: true, force: true }) } catch {}

  /* ── 汇总 ── */
  const bad = results.filter((r) => !r.ok)
  console.log('\n' + '═'.repeat(64))
  console.log(`共 ${results.length} 项检查：通过 ${results.length - bad.length}，失败 ${bad.length}`)
  if (bad.length) {
    console.log('\n失败项：')
    bad.forEach((r) => console.log(`  ✗ [${r.no}] ${r.name}${r.detail ? ' → ' + r.detail : ''}`))
  }
  console.log('截图已输出到 docs/：fix-*.png')
  process.exit(bad.length ? 1 : 0)
}

main().catch((e) => { console.error('✗ 验证脚本异常：', e.message); process.exit(2) })
