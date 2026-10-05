<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NDatePicker, NInput, NInputNumber, NModal, NPopconfirm, NSelect, NSlider, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'
import { countdown } from '../utils/format'

const message = useMessage()
const k = computed(() => store.kaoyan)
const intel = computed(() => store.kaoyanIntel.data)
const now = ref(Date.now())
let timer = null
onMounted(() => {
  timer = setInterval(() => (now.value = Date.now()), 1000)
  if (!store.kaoyanIntel.loaded && !store.kaoyanIntel.loading) store.loadKaoyanIntel()
})
onUnmounted(() => clearInterval(timer))

const cd = computed(() => (k.value.examDate ? countdown(k.value.examDate, now.value) : { text: '待设定', overdue: false }))

const gaps = computed(() =>
  k.value.subjects.map((s) => ({
    ...s,
    gap: s.gap ?? s.target - s.current,
    rate: s.rate ?? (s.target ? Math.round((s.current / s.target) * 100) : 0),
  })),
)

/* 分数达成对比图 */
const scoreOption = computed(() => ({
  grid: { left: 40, right: 16, top: 28, bottom: 26 },
  legend: { data: ['当前预估', '目标分'], textStyle: { color: '#9ca3af', fontSize: 11 }, top: 0, right: 0 },
  xAxis: { type: 'category', data: gaps.value.map((g) => g.name), ...axisBase(), splitLine: { show: false } },
  yAxis: { type: 'value', ...axisBase() },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    { name: '当前预估', ...glowBar(store.settings.accent), data: gaps.value.map((g) => g.current), barWidth: '28%' },
    { name: '目标分', ...glowBar('#60a5fa'), data: gaps.value.map((g) => g.target), barWidth: '28%' },
  ],
}))

/* 阶段推进图 */
const phaseOption = computed(() => ({
  grid: { left: 60, right: 24, top: 10, bottom: 24 },
  xAxis: { type: 'value', max: 100, ...axisBase() },
  yAxis: { type: 'category', data: k.value.phases.map((p) => p.name), ...axisBase(), splitLine: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    {
      type: 'bar', barWidth: 16,
      data: k.value.phases.map((p) => ({
        value: p.done,
        itemStyle: { borderRadius: [0, 6, 6, 0], color: p.color, shadowColor: p.color + '99', shadowBlur: 12 },
      })),
      label: { show: true, position: 'right', color: '#9ca3af', fontSize: 11, formatter: '{c}%' },
    },
  ],
}))

const tasks = ref(store.kaoyan.dailyTasks.map((t) => ({ ...t })))
const doneMinutes = computed(() => tasks.value.filter((t) => t.done).reduce((s, t) => s + t.minutes, 0))
const totalMinutes = computed(() => tasks.value.reduce((s, t) => s + t.minutes, 0))

/* ── 考研情报（聚焦爬虫）：历年分数线 / 复试 / 就业 ── */
const PIE_PALETTE = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf']

/* 分数线趋势：国家线/复试线折线 + 录取最高/最低区间柱 */
const lineOption = computed(() => {
  const lines = intel.value?.score_lines || []
  return {
    grid: { left: 40, right: 16, top: 30, bottom: 24 },
    legend: { data: ['复试线', '录取最低分', '录取最高分'], textStyle: { color: '#9ca3af', fontSize: 10.5 }, top: 0, right: 0 },
    xAxis: { type: 'category', data: lines.map((l) => `${l.year}`), ...axisBase(), splitLine: { show: false } },
    yAxis: { type: 'value', min: 240, ...axisBase() },
    tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
    series: [
      { name: '复试线', ...glowLine('#f87171'), data: lines.map((l) => l.line), symbolSize: 6 },
      { name: '录取最低分', ...glowLine('#fbbf24'), data: lines.map((l) => l.min), symbolSize: 6 },
      { name: '录取最高分', ...glowLine('#4ade80'), data: lines.map((l) => l.max), symbolSize: 6 },
    ],
  }
})

/* 行业分布环形图 */
const industryOption = computed(() => {
  const ind = intel.value?.employment?.industry || []
  return {
    tooltip: { trigger: 'item', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 }, formatter: '{b}<br/>占比约 {c}%' },
    series: [{
      type: 'pie', radius: ['46%', '70%'], center: ['50%', '46%'],
      itemStyle: { borderColor: '#1e1e1e', borderWidth: 2 },
      label: { show: true, color: '#9ca3af', fontSize: 10, formatter: '{b}\n{c}%' },
      labelLine: { length: 6, length2: 8 },
      data: ind.map((c, i) => ({
        name: c.name, value: c.share,
        itemStyle: { color: PIE_PALETTE[i % PIE_PALETTE.length], shadowColor: PIE_PALETTE[i % PIE_PALETTE.length] + '88', shadowBlur: 10 },
      })),
    }],
  }
})

const singleLine = computed(() => {
  const sl = intel.value?.single_line || {}
  const years = Object.keys(sl).sort()
  const y = years[years.length - 1]
  return y ? { year: y, ...sl[y] } : null
})

/* ── 情报可用性：分块判断，任一模块有数据即渲染（避免一个模块缺失导致整页空白）── */
const intelReady = computed(() => !!intel.value && intel.value.available === true)
const hasScoreLines = computed(() => (intel.value?.score_lines?.length || 0) > 0)
const hasRetest = computed(() => {
  const r = intel.value?.retest
  return !!r && (!!r.formula || (r.content?.length || 0) > 0)
})
const hasEmployment = computed(() => {
  const e = intel.value?.employment
  return !!e && ((e.industry?.length || 0) > 0
    || (e.companies?.length || 0) > 0
    || (e.positions?.length || 0) > 0
    || (e.rate_3y?.length || 0) > 0)
})

/* 目标卡内"录取情报速览"条：取最新一年的分数线数据 */
const intelSummary = computed(() => {
  const it = intel.value
  if (!it || !it.available || !it.score_lines || !it.score_lines.length) return null
  const latest = [...it.score_lines].sort((a, b) => b.year - a.year)[0]
  // 无录取最低分时以当年复试线为参照（国家线兜底院校）
  const minAdmit = latest.min ?? it.retest?.min_admitted?.[String(latest.year)] ?? latest.line
  if (latest.line == null) return null
  const rates = it.employment?.rate_3y || []
  const empRate = rates.length ? rates[rates.length - 1].rate : null
  return {
    year: latest.year,
    line: latest.line,
    minAdmit,
    minIsLine: latest.min == null && it.retest?.min_admitted?.[String(latest.year)] == null,
    gapToMin: minAdmit - (k.value.totalCurrent || 0),
    admit: latest.admit ?? '—',
    empRate,
  }
})

/* 剩余天数与每日提分测算（填充目标卡留白） */
const daysLeft = computed(() => {
  if (!k.value.examDate) return null
  const d = Math.ceil((new Date(k.value.examDate).getTime() - now.value) / 86400000)
  return d > 0 ? d : 0
})
const sprint = computed(() => {
  const s = intelSummary.value
  if (!s || !daysLeft.value) return null
  const gap = s.minAdmit - (k.value.totalCurrent || 0)
  return { ok: gap <= 0, gap, days: daysLeft.value, perDay: gap > 0 ? (gap / daysLeft.value).toFixed(2) : '0' }
})

/* 目标卡内迷你趋势图：历年复试线 + 当前预估参考线 */
const miniTrendOption = computed(() => {
  const lines = [...(intel.value?.score_lines || [])].sort((a, b) => a.year - b.year)
  return {
    grid: { left: 34, right: 12, top: 16, bottom: 20 },
    xAxis: { type: 'category', data: lines.map((l) => `${l.year}`), ...axisBase(), splitLine: { show: false }, axisLabel: { color: '#6b7280', fontSize: 10 } },
    yAxis: { type: 'value', min: 240, ...axisBase(), axisLabel: { color: '#6b7280', fontSize: 10 } },
    tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 11 } },
    series: [{
      ...glowLine('#f87171'), data: lines.map((l) => l.line), symbolSize: 5,
      areaStyle: { opacity: 0.08 },
      markLine: {
        silent: true, symbol: 'none', lineStyle: { color: '#60a5fa', type: 'dashed', width: 1 },
        label: { color: '#60a5fa', fontSize: 9.5, formatter: '当前预估' },
        data: [{ yAxis: k.value.totalCurrent }],
      },
    }],
  }
})

function fmtCrawled(iso) {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 16)
}

// 勾选状态写回后端（/kaoyan/plan/tasks/{id}），并同步刷新
async function toggleTask(i) {
  const task = tasks.value[i]
  if (!task.id) {
    task.done = !task.done
    return
  }
  task.done = !task.done
  try {
    await store.toggleKaoyanTask(task.id, task.done)
    message.success(task.done ? '已勾选，坚持就是优势 ✦' : '已取消勾选')
  } catch (err) {
    task.done = !task.done
    message.error(err.message)
  }
}

/* ── 每日任务：新增 / 删除 ── */
const showAddTask = ref(false)
const savingTask = ref(false)
const tf = ref({ phase_id: null, title: '', subject: '综合', minutes: 60 })
const subjectOptions = computed(() =>
  (k.value.subjects || []).map((s) => ({ label: s.name, value: s.name })))
const phaseOptions = computed(() =>
  (k.value.phases || []).map((p) => ({ label: `${p.name}（${p.done}%）`, value: p.id })))

function openAddTask() {
  if (!k.value.phases.length) { message.warning('尚无阶段计划，请先生成或添加阶段'); return }
  tf.value = { phase_id: k.value.phases.find((p) => p.current)?.id ?? k.value.phases[0]?.id ?? null, title: '', subject: '综合', minutes: 60 }
  showAddTask.value = true
}
async function addTask() {
  if (!tf.value.title.trim()) { message.warning('请填写任务内容'); return }
  savingTask.value = true
  try {
    await store.addKaoyanTask({
      phase_id: tf.value.phase_id, title: tf.value.title.trim(),
      subject: tf.value.subject || '综合', minutes: Number(tf.value.minutes) || 60,
    })
    message.success('每日任务已添加')
    showAddTask.value = false
    tasks.value = store.kaoyan.dailyTasks.map((t) => ({ ...t }))
  } catch (err) {
    message.error('添加失败：' + err.message)
  } finally {
    savingTask.value = false
  }
}
async function removeTask(t, i) {
  if (!t.id) { tasks.value.splice(i, 1); return }
  try {
    await store.removeKaoyanTask(t.id)
    message.success('任务已删除')
    tasks.value = store.kaoyan.dailyTasks.map((x) => ({ ...x }))
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 成绩录入 ── */
const showScore = ref(false)
const savingScore = ref(false)
const sf = ref({ subject: '', current: null, mock_name: '', add_study_record: false, minutes: 0 })
function openScore(s) {
  sf.value = { subject: s?.name || k.value.subjects[0]?.name || '', current: s?.current ?? null, mock_name: '', add_study_record: false, minutes: 0 }
  showScore.value = true
}
async function saveScore() {
  if (!sf.value.subject) { message.warning('请选择科目'); return }
  if (sf.value.current === null || sf.value.current === '') { message.warning('请填写当前得分'); return }
  savingScore.value = true
  try {
    await store.recordKaoyanScore({
      subject: sf.value.subject, current: Number(sf.value.current),
      mock_name: sf.value.mock_name.trim() || null,
      add_study_record: sf.value.add_study_record,
      minutes: Number(sf.value.minutes) || 0,
    })
    message.success(`「${sf.value.subject}」成绩已录入，差距分析已重算`)
    showScore.value = false
  } catch (err) {
    message.error('录入失败：' + err.message)
  } finally {
    savingScore.value = false
  }
}

/* ── 阶段管理：新增 / 进度 / 删除 ── */
const showPhase = ref(false)
const phaseEditing = ref(null)
const savingPhase = ref(false)
const pf = ref({ name: '', start_date: null, end_date: null, focus: '', progress: 0 })
function newPhase() {
  phaseEditing.value = null
  pf.value = { name: '', start_date: null, end_date: null, focus: '', progress: 0 }
  showPhase.value = true
}
function editPhase(p) {
  phaseEditing.value = p
  pf.value = { name: p.name, start_date: p.range.split(' ~ ')[0] !== '—' ? p.range.split(' ~ ')[0] : null,
               end_date: p.range.split(' ~ ')[1] !== '—' ? p.range.split(' ~ ')[1] : null,
               focus: p.focus || '', progress: p.done }
  showPhase.value = true
}
function toYMD(ts) {
  if (!ts) return null
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
async function savePhase() {
  if (!pf.value.name.trim()) { message.warning('阶段名称必填'); return }
  savingPhase.value = true
  try {
    const payload = {
      name: pf.value.name.trim(),
      start_date: toYMD(pf.value.start_date),
      end_date: toYMD(pf.value.end_date),
      focus: pf.value.focus.trim() || null,
      progress: Number(pf.value.progress) || 0,
    }
    if (phaseEditing.value) await store.updateKaoyanPhase(phaseEditing.value.id, payload)
    else await store.createKaoyanPhase(payload)
    message.success('阶段已保存')
    showPhase.value = false
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingPhase.value = false
  }
}
async function removePhase(p) {
  try {
    await store.removeKaoyanPhase(p.id)
    message.success(`已删除阶段「${p.name}」及其任务`)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 计划生成参数 ── */
const showGen = ref(false)
const gf = ref({ totalWeeks: 16, dailyMinutes: 300, useAi: true, replaceExisting: false })
const generating = ref(false)
async function generatePlan() {
  generating.value = true
  try {
    const result = await store.kaoyanGeneratePlan({ ...gf.value })
    message.success(`已生成 ${result.phases} 个阶段、${result.daily_tasks} 条每日任务（来源：${result.source === 'ai' ? 'DeepSeek' : '规则引擎'}）`)
    tasks.value = store.kaoyan.dailyTasks.map((t) => ({ ...t }))
    showGen.value = false
  } catch (err) {
    message.error(err.message)
  } finally {
    generating.value = false
  }
}

/* ── 目标录入 / 编辑 ── */
const showGoal = ref(false)
const saving = ref(false)
const degreeOptions = [
  { label: '学硕', value: '学硕' },
  { label: '专硕', value: '专硕' },
]
const gform = ref({ school: '', major: '', degree_type: '学硕', exam_date: null, subjects: [] })

function openGoal() {
  gform.value = {
    school: k.value.school === '—' ? '' : k.value.school,
    major: k.value.major === '—' ? '' : k.value.major,
    degree_type: k.value.degreeType || '学硕',
    exam_date: k.value.examDate || null,
    subjects: k.value.subjects.length
      ? k.value.subjects.map((s) => ({ subject: s.name, target: s.target, current: s.current, max: s.max, line: s.line }))
      : [
          { subject: '政治', target: 75, current: 0, max: 100, line: null },
          { subject: '英语一', target: 80, current: 0, max: 100, line: null },
          { subject: '数学一', target: 130, current: 0, max: 150, line: null },
          { subject: '408 计算机', target: 135, current: 0, max: 150, line: null },
        ],
  }
  showGoal.value = true
}

function addSubject() {
  gform.value.subjects.push({ subject: '', target: 100, current: 0, max: 100, line: null })
}

function removeSubject(i) {
  gform.value.subjects.splice(i, 1)
}

async function saveGoal() {
  if (!gform.value.school.trim() || !gform.value.major.trim()) {
    message.warning('请填写目标院校与专业')
    return
  }
  saving.value = true
  try {
    await store.saveKaoyanTarget({
      school: gform.value.school.trim(),
      major: gform.value.major.trim(),
      degree_type: gform.value.degree_type,
      exam_date: gform.value.exam_date || null,
      subject_scores: gform.value.subjects
        .filter((s) => s.subject && s.subject.trim())
        .map((s) => ({
          subject: s.subject.trim(),
          target: Number(s.target) || 0,
          current: Number(s.current) || 0,
          max: Number(s.max) || 100,
          line: s.line === null || s.line === undefined ? null : Number(s.line),
        })),
    })
    message.success('目标已保存，差距分析与阶段计划已同步更新')
    showGoal.value = false
    store.loadKaoyanIntel(true)   // 目标院校/专业已变更，重新抓取情报
  } catch (err) {
    message.error(err.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>考研规划</h2>
      <span class="sub mono">STRATEGY · {{ k.school }} {{ k.major }}</span>
      <span class="spacer" />
      <span v-if="!k.hasTarget" class="chip chip-yellow">尚未录入目标 · 请先设定</span>
      <NButton size="small" secondary type="primary" :loading="store.kaoyanIntel.loading" @click="store.loadKaoyanIntel(true)">
        ↻ 刷新情报
      </NButton>
      <NButton size="small" type="primary" ghost @click="openGoal">
        {{ k.hasTarget ? '编辑目标' : '录入目标' }}
      </NButton>
      <span class="chip chip-red">距初试 {{ cd.text }}</span>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <section class="col-8 card target-card">
        <div class="t-left">
          <div class="label-3">目标院校 / 专业</div>
          <div class="t-school">{{ k.school }}</div>
          <div class="t-major">{{ k.major }}</div>
          <div class="t-tags">
            <span class="chip chip-accent">{{ k.degreeType }} · {{ k.subjects.length }} 科</span>
            <span class="chip chip-blue">目标总分 {{ k.totalTarget }}</span>
            <span class="chip chip-yellow">当前预估 {{ k.totalCurrent }}</span>
          </div>

          <!-- 各科达成率（填充卡片空间，一眼看出薄弱科目） -->
          <div v-if="gaps.length" class="t-subjects">
            <div v-for="g in gaps" :key="g.name" class="ts-row">
              <span class="ts-name">{{ g.name }}</span>
              <div class="ts-bar">
                <div class="ts-fill" :style="{
                  width: Math.min(100, g.rate) + '%',
                  background: g.gap > 40 ? '#f87171' : g.gap > 25 ? '#fbbf24' : '#4ade80',
                }" />
              </div>
              <span class="ts-num mono">{{ g.current }}/{{ g.target }}</span>
              <span class="ts-gap mono" :class="g.gap > 40 ? 'red' : g.gap > 25 ? 'yellow' : 'green'">
                差 {{ g.gap }}
              </span>
            </div>
          </div>

          <!-- 录取情报速览（聚焦爬虫抓取院校公开数据，填充卡片留白） -->
          <div v-if="intelSummary" class="intel-strip">
            <div class="is-item">
              <span class="label-3">{{ intelSummary.year }} 复试线</span>
              <b class="mono is-red">{{ intelSummary.line }}</b>
            </div>
            <span class="is-sep" />
            <div class="is-item">
              <span class="label-3">{{ intelSummary.minIsLine ? `${intelSummary.year} 复试线（参照）` : '去年录取最低分' }}</span>
              <b class="mono is-yellow">{{ intelSummary.minAdmit }}</b>
            </div>
            <span class="is-sep" />
            <div class="is-item">
              <span class="label-3">当前预估距{{ intelSummary.minIsLine ? '复试线' : '最低分' }}</span>
              <b class="mono" :class="intelSummary.gapToMin > 0 ? 'is-red' : 'is-green'">
                {{ intelSummary.gapToMin > 0 ? `差 ${intelSummary.gapToMin}` : `超 ${-intelSummary.gapToMin}` }}
              </b>
            </div>
            <template v-if="intelSummary.admit !== '—'">
              <span class="is-sep" />
              <div class="is-item">
                <span class="label-3">去年一志愿录取</span>
                <b class="mono">{{ intelSummary.admit }} 人</b>
              </div>
            </template>
            <template v-if="intelSummary.empRate != null">
              <span class="is-sep" />
              <div class="is-item">
                <span class="label-3">学院就业率</span>
                <b class="mono is-green">{{ intelSummary.empRate }}%</b>
              </div>
            </template>
            <div class="is-src mono">数据来源：{{ intel.source }} · 采集 {{ fmtCrawled(intel.crawled_at) }}</div>
          </div>
          <!-- 迷你趋势 + 冲刺测算（填充卡片下部空间） -->
          <div v-if="intelSummary" class="t-sprint">
            <div class="sp-chart">
              <div class="label-3" style="margin-bottom:2px">历年复试线走势</div>
              <GlowChart :option="miniTrendOption" height="128px" />
            </div>
            <div v-if="sprint" class="sp-metrics">
              <div class="sp-item">
                <span class="label-3">剩余天数</span>
                <b class="mono">{{ sprint.days }} 天</b>
              </div>
              <div class="sp-item">
                <span class="label-3">{{ sprint.ok ? '状态' : '每日需提分' }}</span>
                <b class="mono" :class="sprint.ok ? 'is-green' : 'is-yellow'">
                  {{ sprint.ok ? '已过参照线' : `+${sprint.perDay} 分` }}
                </b>
              </div>
              <div class="sp-tip mono">
                {{ sprint.ok
                  ? '当前预估已超过参照线，稳住节奏、向更高目标分冲刺'
                  : `距参照线还差 ${sprint.gap} 分 · 按 4 科均摊，每天多拿 ${sprint.perDay} 分即可追平` }}
              </div>
            </div>
          </div>
          <!-- 无情报时的占位提示（引导刷新，避免卡片空洞） -->
          <div v-else-if="!store.kaoyanIntel.loading" class="intel-empty">
            <div class="ie-icon">◌</div>
            <div class="ie-text">
              暂无「{{ k.school }} · {{ k.major }}」的院校情报<br>
              点击右上角 <b>↻ 刷新情报</b> 通过爬虫抓取该校公开数据（历年分数线 / 复试规则 / 就业），抓取结果自动存入数据库，随时可查看
            </div>
          </div>
        </div>
        <div class="t-right">
          <div class="ring-wrap">
            <div class="ring-num num-big">{{ store.studyOverview.kaoyanProgress }}%</div>
            <div class="label-3">总进度</div>
          </div>
          <div class="cd-box">
            <div class="label-3">距初试</div>
            <div class="cd-num mono">{{ cd.text }}</div>
            <div class="label-3">{{ k.examDate ? k.examDate.slice(0, 10) : '初试日期待设定' }} 08:30</div>
          </div>
        </div>
      </section>

      <section class="col-4 card">
        <header class="card-head">
          <div class="card-title">◱ 阶段推进 <span class="en">PHASES</span></div>
          <NButton size="tiny" quaternary type="primary" @click="newPhase">＋ 阶段</NButton>
        </header>
        <GlowChart :option="phaseOption" height="176px" />
        <div v-for="p in k.phases" :key="p.name" class="phase-row">
          <span class="dot" :style="{ background: p.color, boxShadow: `0 0 8px ${p.color}` }" />
          <div class="ph-mid">
            <div class="ph-name">{{ p.name }} <span v-if="p.current" class="chip chip-accent">进行中</span></div>
            <div class="ph-focus mono">{{ p.range }} · {{ p.focus }}</div>
          </div>
          <div class="ph-pct mono" :style="{ color: p.color }">{{ p.done }}%</div>
          <div class="ph-ops">
            <button class="ph-btn" title="编辑阶段" @click="editPhase(p)">✎</button>
            <NPopconfirm @positive-click="removePhase(p)">
              <template #trigger><button class="ph-btn del" title="删除阶段">✕</button></template>
              删除「{{ p.name }}」？其下每日任务一并删除。
            </NPopconfirm>
          </div>
        </div>
      </section>
    </div>

    <!-- ── 考研情报：历年分数线 / 复试 / 就业（聚焦爬虫抓取） ── -->
    <div v-if="store.kaoyanIntel.loading && !intel" class="grid" style="margin-bottom: 16px">
      <section class="col-12 card intel-loading mono">◌ 正在抓取目标院校公开数据（分数线 / 复试 / 就业）…</section>
    </div>
    <template v-if="intelReady">
      <div v-if="hasScoreLines || hasRetest" class="grid" style="margin-bottom: 16px">
        <section v-if="hasScoreLines" class="col-8 card">
          <header class="card-head">
            <div class="card-title">◔ 历年录取分数线 <span class="en">CUTOFF HISTORY</span></div>
            <div style="display:flex; gap:8px; align-items:center">
              <span class="chip chip-blue mono">{{ intel.major_code }} · {{ intel.degree }}</span>
              <NButton size="tiny" quaternary type="primary" :loading="store.kaoyanIntel.loading" @click="store.loadKaoyanIntel(true)">↻ 更新</NButton>
            </div>
          </header>
          <GlowChart :option="lineOption" height="180px" />
          <div class="sl-table">
            <div class="sl-row sl-head mono">
              <span>年份</span><span>复试线</span><span>类型</span><span>报考</span><span>录取</span><span>最高分</span><span>最低分</span><span>平均分</span>
            </div>
            <div v-for="l in intel.score_lines" :key="l.year" class="sl-row">
              <span class="sl-year">{{ l.year }}</span>
              <span class="sl-line">{{ l.line }}</span>
              <span class="sl-type">{{ l.line_type }}</span>
              <span>{{ l.report ?? '—' }}</span>
              <span>{{ l.admit ?? '—' }}</span>
              <span>{{ l.max ?? '—' }}</span>
              <span class="sl-min">{{ l.min ?? '—' }}</span>
              <span>{{ l.avg ?? '—' }}</span>
            </div>
          </div>
          <div v-if="singleLine" class="single-line mono">
            {{ singleLine.year }} 单科线（A类工学）：政治 ≥ {{ singleLine.politics }} · 外语 ≥ {{ singleLine.foreign }} · 业务课一 ≥ {{ singleLine.paper1 }} · 业务课二 ≥ {{ singleLine.paper2 }}
            <span class="chip chip-accent" style="margin-left:6px">{{ intel.exam_subjects }}</span>
          </div>
          <div class="intel-src mono">来源：{{ intel.source }} · 采集 {{ fmtCrawled(intel.crawled_at) }}{{ intel.from_cache ? '（缓存）' : '' }}</div>
        </section>

        <section v-if="hasRetest" class="col-4 card" :class="{ 'col-12': !hasScoreLines }">
          <header class="card-head"><div class="card-title">◈ 复试与录取规则 <span class="en">RETEST</span></div></header>
          <div class="rt-formula mono">{{ intel.retest.formula }}</div>
          <div class="rt-items">
            <div v-for="it in intel.retest.content" :key="it.item" class="rt-item">
              <span class="rt-name">{{ it.item }}</span>
              <div class="rt-bar"><div class="rt-fill" :style="{ width: (it.score / 300 * 100) + '%' }" /></div>
              <span class="rt-num mono">{{ it.score }}分</span>
            </div>
            <div v-if="!intel.retest.content?.length" class="rt-empty mono">该校未公布复试科目分值构成，以研究生院复试细则为准</div>
          </div>
          <div class="rt-rule">
            <div class="rt-rule-row"><span class="label-3">差额比例</span><span>{{ intel.retest.ratio }}</span></div>
            <div class="rt-rule-row"><span class="label-3">录取原则</span><span>{{ intel.retest.rule }}</span></div>
            <div class="rt-rule-row"><span class="label-3">近年录取最低分</span>
              <span class="mono">{{ Object.entries(intel.retest.min_admitted || {}).map(([y, v]) => `${y}:${v}`).join(' · ') || '—' }}</span>
            </div>
          </div>
        </section>
      </div>

      <div v-if="hasEmployment" class="grid" style="margin-bottom: 16px">
        <section class="col-5 card">
          <header class="card-head">
            <div class="card-title">◱ 行业分布与就业率 <span class="en">INDUSTRY</span></div>
            <span v-if="intel.employment.rate_3y?.length" class="chip chip-accent">近3年平均 {{ (intel.employment.rate_3y.reduce((s, r) => s + r.rate, 0) / intel.employment.rate_3y.length).toFixed(1) }}%</span>
            <span v-else-if="intel.employment.profile_label" class="chip chip-blue">{{ intel.employment.profile_label }}画像</span>
          </header>
          <GlowChart v-if="intel.employment.industry?.length" :option="industryOption" height="200px" />
          <div v-if="intel.employment.rate_3y?.length" class="emp-rate-row">
            <div v-for="r in intel.employment.rate_3y" :key="r.year" class="er-item">
              <div class="er-year mono">{{ r.year }}</div>
              <div class="er-rate mono" :style="{ color: r.rate >= 96 ? '#4ade80' : '#fbbf24' }">{{ r.rate }}%</div>
            </div>
          </div>
          <div class="intel-src mono">{{ intel.employment.salary_note }}</div>
        </section>

        <section class="col-7 card">
          <header class="card-head"><div class="card-title">☰ 主要就业单位与岗位 <span class="en">EMPLOYERS</span></div></header>
          <div class="emp-grid">
            <div v-for="(c, ci) in (intel.employment.companies || [])" :key="c.name" class="emp-card">
              <div class="emp-logo mono" :style="{ color: PIE_PALETTE[ci % PIE_PALETTE.length] }">{{ (c.name || '—').slice(0, 2) }}</div>
              <div class="emp-mid">
                <div class="emp-name">{{ c.name }}</div>
                <div class="emp-roles mono">{{ c.roles }}</div>
              </div>
              <span class="chip">{{ c.industry }}</span>
            </div>
          </div>
          <div v-if="intel.employment.positions?.length" class="pos-tags">
            <span class="label-3" style="margin-right:6px">典型岗位</span>
            <span v-for="p in intel.employment.positions" :key="p" class="chip chip-blue">{{ p }}</span>
          </div>
          <div class="intel-src mono">来源：{{ intel.source }} · 采集 {{ fmtCrawled(intel.crawled_at) }}{{ intel.employment.is_estimate ? ' · 就业画像为公开信息估算' : '' }}</div>
        </section>
      </div>
    </template>

    <!-- 情报不可用时的明确提示（不静默留白） -->
    <div v-else-if="!store.kaoyanIntel.loading && intel && !intel.available" class="grid" style="margin-bottom: 16px">
      <section class="col-12 card intel-miss">
        <div class="im-title">◌ 暂未获取到该校情报</div>
        <div class="im-reason">{{ intel.reason || '数据源暂不可用' }}</div>
        <div v-if="intel.hint_sources?.length" class="im-hint mono">
          可参考来源：{{ intel.hint_sources.join(' · ') }}
        </div>
        <NButton size="tiny" type="primary" ghost style="margin-top:10px"
                 :loading="store.kaoyanIntel.loading" @click="store.loadKaoyanIntel(true)">↻ 重新抓取</NButton>
      </section>
    </div>

    <div class="grid">
      <section class="col-7 card">
        <header class="card-head">
          <div class="card-title">◈ 差距分析 <span class="en">GAP ANALYSIS</span></div>
          <div style="display:flex; gap:8px; align-items:center">
            <NButton size="tiny" quaternary type="primary" @click="openScore(null)">✎ 录入成绩</NButton>
            <span class="chip chip-red">总分差 {{ k.totalTarget - k.totalCurrent }}</span>
          </div>
        </header>
        <GlowChart :option="scoreOption" height="216px" />
        <div class="gap-list">
          <div v-for="g in gaps" :key="g.name" class="gap-row">
            <div class="g-name">{{ g.name }}</div>
            <div class="g-bar">
              <div class="g-fill" :style="{ width: g.rate + '%', background: g.gap > 40 ? '#f87171' : g.gap > 25 ? '#facc15' : '#4ade80' }" />
            </div>
            <div class="g-num mono">{{ g.current }} / {{ g.target }}</div>
            <div class="chip" :class="g.gap > 40 ? 'chip-red' : g.gap > 25 ? 'chip-yellow' : 'chip-accent'">差 {{ g.gap }}</div>
            <button class="ph-btn" title="录入该科最新成绩" @click="openScore(g)">✎</button>
          </div>
        </div>
      </section>

      <section class="col-5 card">
        <header class="card-head">
          <div class="card-title">☑ 今日任务拆解 <span class="en">DAILY PLAN</span></div>
          <div style="display:flex; gap:8px; align-items:center">
            <NButton size="tiny" quaternary type="primary" @click="openAddTask">＋ 任务</NButton>
            <span class="chip chip-accent mono">{{ doneMinutes }}/{{ totalMinutes }} min</span>
          </div>
        </header>
        <div class="task-list">
          <div v-for="(t, i) in tasks" :key="i" class="task" :class="{ done: t.done }" @click="toggleTask(i)">
            <button class="check" :class="{ on: t.done }">{{ t.done ? '✓' : '' }}</button>
            <div class="tk-mid">
              <div class="tk-text">{{ t.text }}</div>
              <div class="tk-meta mono">
                <span class="chip">{{ t.subject }}</span>
                <span>{{ t.minutes }} 分钟</span>
              </div>
            </div>
            <NPopconfirm @positive-click="removeTask(t, i)">
              <template #trigger>
                <button class="ph-btn del" title="删除任务" @click.stop>✕</button>
              </template>
              删除任务「{{ t.text }}」？
            </NPopconfirm>
          </div>
          <div v-if="!tasks.length" class="empty-task mono">暂无每日任务 · 点「＋ 任务」手动添加，或在下方生成计划</div>
        </div>
        <div v-if="totalMinutes" class="done-bar">
          <div class="db-track"><div class="db-fill" :style="{ width: Math.round((doneMinutes / totalMinutes) * 100) + '%' }" /></div>
          <span class="mono label-3">今日投入完成度 {{ Math.round((doneMinutes / totalMinutes) * 100) }}%</span>
        </div>
      </section>

      <section class="col-12 card">
        <header class="card-head">
          <div class="card-title">✦ AI 周复盘 <span class="en">WEEKLY REVIEW</span></div>
          <NButton size="tiny" type="primary" ghost @click="showGen = true">⚙ 生成计划</NButton>
        </header>
        <p class="review">{{ k.weeklyReview }}</p>
      </section>
    </div>

    <!-- 计划生成参数 -->
    <NModal v-model:show="showGen" preset="card" title="⚙ 生成学习计划" style="width: 460px" :bordered="false">
      <div class="gen-form">
        <div class="field">
          <label class="label-3">剩余备考周数（4~40）</label>
          <NInputNumber v-model:value="gf.totalWeeks" :min="4" :max="40" style="width: 100%" />
        </div>
        <div class="field">
          <label class="label-3">每日可投入分钟（60~900）</label>
          <NInputNumber v-model:value="gf.dailyMinutes" :min="60" :max="900" :step="30" style="width: 100%" />
        </div>
        <label class="gen-opt"><input type="checkbox" v-model="gf.useAi" /> 优先使用 DeepSeek 生成（失败自动回退规则引擎）</label>
        <label class="gen-opt"><input type="checkbox" v-model="gf.replaceExisting" /> 清空旧阶段计划后重新生成</label>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showGen = false">取消</NButton>
          <NButton type="primary" :loading="generating" @click="generatePlan">开始生成</NButton>
        </div>
      </template>
    </NModal>

    <!-- 每日任务新增 -->
    <NModal v-model:show="showAddTask" preset="card" title="＋ 新增每日任务" style="width: 460px" :bordered="false">
      <div class="gen-form">
        <div class="field">
          <label class="label-3">任务内容</label>
          <NInput v-model:value="tf.title" placeholder="如：数学模拟卷 03 + 错题整理" />
        </div>
        <div class="two">
          <div class="field">
            <label class="label-3">科目</label>
            <NSelect v-model:value="tf.subject" :options="subjectOptions" tag filterable />
          </div>
          <div class="field">
            <label class="label-3">时长（分钟）</label>
            <NInputNumber v-model:value="tf.minutes" :min="0" :max="600" :step="15" style="width: 100%" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">归属阶段</label>
          <NSelect v-model:value="tf.phase_id" :options="phaseOptions" />
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showAddTask = false">取消</NButton>
          <NButton type="primary" :loading="savingTask" @click="addTask">添加</NButton>
        </div>
      </template>
    </NModal>

    <!-- 成绩录入 -->
    <NModal v-model:show="showScore" preset="card" title="✎ 录入科目成绩" style="width: 460px" :bordered="false">
      <div class="gen-form">
        <div class="two">
          <div class="field">
            <label class="label-3">科目</label>
            <NSelect v-model:value="sf.subject" :options="subjectOptions" />
          </div>
          <div class="field">
            <label class="label-3">当前得分</label>
            <NInputNumber v-model:value="sf.current" :min="0" :max="500" style="width: 100%" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">考试名称（可选，如「模拟卷 05」）</label>
          <NInput v-model:value="sf.mock_name" placeholder="选填" />
        </div>
        <label class="gen-opt"><input type="checkbox" v-model="sf.add_study_record" /> 同时写入一条学习记录</label>
        <div v-if="sf.add_study_record" class="field">
          <label class="label-3">本次学习时长（分钟）</label>
          <NInputNumber v-model:value="sf.minutes" :min="0" :max="1440" :step="15" style="width: 100%" />
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showScore = false">取消</NButton>
          <NButton type="primary" :loading="savingScore" @click="saveScore">录入</NButton>
        </div>
      </template>
    </NModal>

    <!-- 阶段新增/编辑 -->
    <NModal v-model:show="showPhase" preset="card" :title="phaseEditing ? `✎ 编辑阶段「${phaseEditing.name}」` : '＋ 新增阶段'"
            style="width: 480px" :bordered="false">
      <div class="gen-form">
        <div class="field">
          <label class="label-3">阶段名称</label>
          <NInput v-model:value="pf.name" placeholder="如：强化阶段" />
        </div>
        <div class="two">
          <div class="field">
            <label class="label-3">开始日期</label>
            <NDatePicker v-model:formatted-value="pf.start_date" type="date" value-format="yyyy-MM-dd" clearable style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">结束日期</label>
            <NDatePicker v-model:formatted-value="pf.end_date" type="date" value-format="yyyy-MM-dd" clearable style="width: 100%" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">阶段重心</label>
          <NInput v-model:value="pf.focus" placeholder="如：真题刷题 + 错题闭环" />
        </div>
        <div class="field">
          <label class="label-3">完成进度：{{ pf.progress }}%</label>
          <NSlider v-model:value="pf.progress" :min="0" :max="100" :step="5" />
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showPhase = false">取消</NButton>
          <NButton type="primary" :loading="savingPhase" @click="savePhase">保存</NButton>
        </div>
      </template>
    </NModal>

    <!-- 目标录入 / 编辑弹窗 -->
    <NModal v-model:show="showGoal" preset="card" style="width: 620px" :bordered="false"
            :title="k.hasTarget ? '编辑考研目标' : '录入考研目标'">
      <div class="goal-form">
        <div class="two">
          <div class="field">
            <label class="label-3">目标院校</label>
            <NInput v-model:value="gform.school" placeholder="如：华中科技大学" />
          </div>
          <div class="field">
            <label class="label-3">目标专业</label>
            <NInput v-model:value="gform.major" placeholder="如：计算机科学与技术（学硕）" />
          </div>
          <div class="field">
            <label class="label-3">学位类型</label>
            <NSelect v-model:value="gform.degree_type" :options="degreeOptions" />
          </div>
          <div class="field">
            <label class="label-3">初试日期</label>
            <NDatePicker v-model:formatted-value="gform.exam_date" type="date"
                         value-format="yyyy-MM-dd" clearable style="width: 100%"
                         placeholder="选择初试日期" />
          </div>
        </div>

        <div class="sub-row">
          <span class="label-3">各科分数线与当前成绩</span>
          <NButton size="tiny" quaternary type="primary" @click="addSubject">＋ 添加科目</NButton>
        </div>

        <div class="subj-head mono">
          <span style="flex:1.4">科目</span><span style="width:96px">目标分</span>
          <span style="width:96px">当前分</span><span style="width:96px">满分</span>
          <span style="width:32px"></span>
        </div>
        <div v-for="(s, i) in gform.subjects" :key="i" class="subj-row">
          <NInput v-model:value="s.subject" size="small" placeholder="科目名" style="flex:1.4" />
          <NInputNumber v-model:value="s.target" size="small" :min="0" :max="500" style="width:96px" />
          <NInputNumber v-model:value="s.current" size="small" :min="0" :max="500" style="width:96px" />
          <NInputNumber v-model:value="s.max" size="small" :min="1" :max="500" style="width:96px" />
          <button class="del" title="删除该科目" @click="removeSubject(i)">✕</button>
        </div>

        <div class="hint mono">
          总分目标与当前预估将按各科自动求和；保存后差距分析、阶段计划与总览卡片会立即刷新。
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showGoal = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveGoal">保存目标</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.goal-form { display: flex; flex-direction: column; gap: 14px; }
.goal-form .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.goal-form .field { display: flex; flex-direction: column; gap: 6px; }
.sub-row { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.subj-head, .subj-row { display: flex; align-items: center; gap: 8px; }
.subj-head { font-size: 10.5px; color: var(--text-3); padding: 0 2px 4px; border-bottom: 1px solid var(--border); }
.subj-row { padding: 4px 0; }
.del {
  width: 26px; height: 26px; border-radius: 8px; cursor: pointer; flex-shrink: 0;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 11px;
}
.del:hover { color: var(--red); border-color: rgba(248, 113, 113, 0.4); }
.hint { font-size: 10.5px; color: var(--text-3); }
.footer { display: flex; justify-content: flex-end; gap: 10px; }

.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }

.target-card { display: flex; align-items: stretch; justify-content: space-between; gap: 20px; }
.t-left { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: flex-start; }
.t-subjects { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.ts-row { display: flex; align-items: center; gap: 10px; }
.ts-name { width: 84px; font-size: 12px; color: var(--text-2); flex-shrink: 0; }
.ts-bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.ts-fill { height: 100%; border-radius: 3px; box-shadow: 0 0 10px currentColor; transition: width 0.4s ease; }
.ts-num { font-size: 11px; color: var(--text-3); width: 66px; text-align: right; }
.ts-gap { font-size: 11px; width: 54px; text-align: right; }
.ts-gap.red { color: var(--red); }

/* 目标卡内录取情报速览条 */
.intel-strip { margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--border); display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; }
.t-sprint { margin-top: 12px; display: flex; gap: 18px; align-items: stretch; flex-wrap: wrap; }
.t-sprint .sp-chart { flex: 1.4; min-width: 240px; }
.t-sprint .sp-metrics { flex: 1; min-width: 200px; display: flex; flex-direction: column; justify-content: center; gap: 8px; padding: 10px 14px; border: 1px solid var(--border); border-radius: 10px; background: rgba(255,255,255,0.02); }
.sp-item { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.sp-item b { font-size: 16px; }
.sp-tip { font-size: 11px; color: var(--text-3); line-height: 1.7; }
.intel-empty { margin-top: 16px; padding-top: 12px; border-top: 1px dashed var(--border); display: flex; align-items: flex-start; gap: 10px; color: var(--text-3); font-size: 12px; line-height: 1.8; }
.intel-empty .ie-icon { font-size: 16px; color: var(--accent, #4ade80); animation: spin 3s linear infinite; }
.intel-empty b { color: var(--text-1); }
@keyframes spin { to { transform: rotate(360deg); } }
.is-item { display: flex; flex-direction: column; gap: 2px; min-width: 76px; }
.is-item b { font-size: 15px; font-weight: 700; color: var(--text-1); }
.is-item b.is-red { color: var(--red); }
.is-item b.is-yellow { color: var(--yellow); }
.is-item b.is-green { color: var(--accent); }
.is-sep { width: 1px; height: 26px; background: var(--border); }
.is-src { flex-basis: 100%; font-size: 9.5px; color: var(--text-3); opacity: 0.8; margin-top: 2px; }
.ts-gap.yellow { color: var(--yellow); }
.ts-gap.green { color: var(--accent); }
.t-school { font-size: 22px; font-weight: 700; margin-top: 6px; }
.t-major { color: var(--text-2); font-size: 13px; margin-top: 2px; }
.t-tags { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.t-right { display: flex; gap: 24px; align-items: center; }
.ring-wrap { text-align: center; }
.cd-box { text-align: right; }
.cd-num { font-size: 18px; color: var(--red); text-shadow: 0 0 14px rgba(248, 113, 113, 0.4); margin: 4px 0; }

.phase-row { display: flex; align-items: center; gap: 10px; padding: 7px 2px; border-top: 1px dashed var(--border); }
.ph-mid { flex: 1; min-width: 0; }
.ph-name { font-size: 12.5px; display: flex; align-items: center; gap: 6px; }
.ph-focus { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.ph-pct { font-size: 12px; }

.gap-list { margin-top: 10px; }
.gap-row { display: flex; align-items: center; gap: 12px; padding: 6px 2px; }
.g-name { width: 74px; font-size: 12.5px; color: var(--text-2); }
.g-bar { flex: 1; height: 8px; border-radius: 4px; background: #262626; overflow: hidden; }
.g-fill { height: 100%; border-radius: 4px; box-shadow: 0 0 10px currentColor; transition: width 0.4s ease; }
.g-num { font-size: 11px; color: var(--text-3); width: 84px; text-align: right; }

.task-list { display: flex; flex-direction: column; }
.task { display: flex; align-items: center; gap: 10px; padding: 9px 2px; border-bottom: 1px dashed var(--border); cursor: pointer; }
.task:last-child { border-bottom: none; }
.task.done { opacity: 0.5; }
.task.done .tk-text { text-decoration: line-through; }
.check {
  width: 19px; height: 19px; border-radius: 6px; flex-shrink: 0; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--accent); font-size: 11px;
}
.check.on { background: var(--accent); border-color: var(--accent); color: #05130a; font-weight: 700; }
.tk-mid { flex: 1; min-width: 0; }
.tk-text { font-size: 12.5px; }
.tk-meta { display: flex; align-items: center; gap: 8px; font-size: 10px; color: var(--text-3); margin-top: 3px; }

.done-bar { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; }
.db-track { height: 6px; border-radius: 3px; background: #262626; overflow: hidden; margin-bottom: 6px; }
.db-fill { height: 100%; background: var(--accent); box-shadow: 0 0 10px var(--accent); transition: width 0.3s ease; }

.review { margin: 0; color: var(--text-2); font-size: 13px; line-height: 1.9; }

.gen-form { display: flex; flex-direction: column; gap: 14px; }
.gen-form .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.gen-form .field { display: flex; flex-direction: column; gap: 6px; }
.gen-opt { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); cursor: pointer; }
.gen-opt input { accent-color: var(--accent); }

.ph-ops { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.ph-btn {
  width: 24px; height: 24px; border-radius: 7px; cursor: pointer; flex-shrink: 0;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 11px;
}
.ph-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.ph-btn.del:hover { color: var(--red); border-color: rgba(248, 113, 113, 0.4); }

.empty-task { padding: 26px 0; text-align: center; font-size: 11.5px; color: var(--text-3); }

/* ── 考研情报卡片 ── */
.intel-loading { padding: 22px; text-align: center; font-size: 11.5px; color: var(--text-3); }

/* 情报不可用提示 */
.intel-miss { text-align: center; padding: 22px 20px; }
.im-title { font-size: 13.5px; color: var(--text-1); font-weight: 600; }
.im-reason { margin-top: 6px; font-size: 12px; color: var(--text-2); }
.im-hint { margin-top: 8px; font-size: 10.5px; color: var(--text-3); }
.rt-empty { font-size: 11px; color: var(--text-3); padding: 6px 0; }
.sl-table { margin-top: 10px; border-top: 1px solid var(--border); }
.sl-row { display: grid; grid-template-columns: 52px 56px 1fr 52px 52px 58px 58px 64px; align-items: center; gap: 6px; padding: 6px 2px; font-size: 11.5px; color: var(--text-2); border-bottom: 1px dashed var(--border); }
.sl-row:last-child { border-bottom: none; }
.sl-head { color: var(--text-3); font-size: 10.5px; }
.sl-year { font-weight: 600; color: var(--text-1); }
.sl-line { color: var(--red); font-weight: 600; }
.sl-type { font-size: 10.5px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sl-min { color: var(--yellow); }
.single-line { margin-top: 10px; font-size: 10.5px; color: var(--text-3); line-height: 1.8; }
.intel-src { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: 10px; color: var(--text-3); line-height: 1.7; }

.rt-formula { font-size: 11px; color: var(--accent); line-height: 1.8; padding: 8px 10px; border-radius: 8px; background: rgba(74, 222, 128, 0.06); border: 1px solid rgba(74, 222, 128, 0.18); }
.rt-items { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.rt-item { display: flex; align-items: center; gap: 10px; }
.rt-name { width: 64px; font-size: 12px; color: var(--text-2); flex-shrink: 0; }
.rt-bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.rt-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #60a5fa, #c084fc); box-shadow: 0 0 10px rgba(96, 165, 250, 0.5); }
.rt-num { width: 44px; text-align: right; font-size: 11px; color: var(--text-3); }
.rt-rule { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.rt-rule-row { display: flex; flex-direction: column; gap: 2px; font-size: 11.5px; color: var(--text-2); line-height: 1.6; }

.emp-rate-row { display: flex; gap: 10px; margin-top: 10px; }
.er-item { flex: 1; text-align: center; padding: 8px 4px; border-radius: 10px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); }
.er-year { font-size: 10px; color: var(--text-3); }
.er-rate { font-size: 15px; font-weight: 700; margin-top: 2px; }

.emp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.emp-card { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 10px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); min-width: 0; transition: border-color 0.2s ease; }
.emp-card:hover { border-color: rgba(74, 222, 128, 0.35); }
.emp-logo { width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border); }
.emp-mid { flex: 1; min-width: 0; }
.emp-name { font-size: 12.5px; font-weight: 600; }
.emp-roles { font-size: 10px; color: var(--text-3); margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pos-tags { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

@media (max-width: 860px) {
  .emp-grid { grid-template-columns: 1fr; }
  .sl-row { grid-template-columns: 44px 48px 1fr 44px 44px 50px 50px 56px; }
}
</style>
