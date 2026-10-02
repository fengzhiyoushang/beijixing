<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NDatePicker, NInput, NInputNumber, NModal, NPopconfirm, NSelect, NSlider, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'
import { countdown } from '../utils/format'

const message = useMessage()
const k = computed(() => store.kaoyan)
const now = ref(Date.now())
let timer = null
onMounted(() => { timer = setInterval(() => (now.value = Date.now()), 1000) })
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

.target-card { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.t-left { flex: 1; min-width: 0; }
.t-subjects { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.ts-row { display: flex; align-items: center; gap: 10px; }
.ts-name { width: 84px; font-size: 12px; color: var(--text-2); flex-shrink: 0; }
.ts-bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.ts-fill { height: 100%; border-radius: 3px; box-shadow: 0 0 10px currentColor; transition: width 0.4s ease; }
.ts-num { font-size: 11px; color: var(--text-3); width: 66px; text-align: right; }
.ts-gap { font-size: 11px; width: 54px; text-align: right; }
.ts-gap.red { color: var(--red); }
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
</style>
