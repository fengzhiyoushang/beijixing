<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NDatePicker, NInput, NInputNumber, NModal, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'
import { countdown, PRIORITY_LABEL, PRIORITY_TONE } from '../utils/format'

const message = useMessage()
const now = ref(Date.now())
let timer = null
onMounted(() => { timer = setInterval(() => (now.value = Date.now()), 1000) })
onUnmounted(() => clearInterval(timer))

const filter = ref('all')
const filters = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待推进' },
  { key: 'today', label: '今日到期' },
  { key: 'overdue', label: '已逾期' },
  { key: 'done', label: '已完成' },
]

const priorityWeight = { high: 0, medium: 1, low: 2 }

const list = computed(() => {
  const endOfDay = new Date(); endOfDay.setHours(23, 59, 59, 999)
  let arr = store.notes.slice()
  if (filter.value === 'pending') arr = arr.filter((n) => n.status === 'pending')
  else if (filter.value === 'done') arr = arr.filter((n) => n.status === 'done')
  else if (filter.value === 'today') arr = arr.filter((n) => n.status === 'pending' && n.due && new Date(n.due) <= endOfDay)
  else if (filter.value === 'overdue') arr = arr.filter((n) => n.status === 'pending' && n.due && new Date(n.due) < new Date())
  return arr.sort(
    (a, b) =>
      (a.status === 'done' ? 1 : 0) - (b.status === 'done' ? 1 : 0) ||
      priorityWeight[a.priority] - priorityWeight[b.priority] ||
      new Date(a.due || 8e15) - new Date(b.due || 8e15),
  )
})

const stats = computed(() => store.noteStats)

/* 图 1：完成 / 新建 趋势 */
const trendOption = computed(() => ({
  grid: { left: 34, right: 14, top: 26, bottom: 26 },
  legend: { data: ['完成', '新建'], textStyle: { color: '#9ca3af', fontSize: 11 }, top: 0, right: 0 },
  xAxis: { type: 'category', data: stats.value.doneTrend.days, ...axisBase(), splitLine: { show: false } },
  yAxis: { type: 'value', ...axisBase() },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    { name: '完成', ...glowBar(store.settings.accent), data: stats.value.doneTrend.done, barWidth: '34%' },
    { name: '新建', ...glowLine('#60a5fa'), data: stats.value.doneTrend.created },
  ],
}))

/* 图 2：分类占比（真实数据） */
const PALETTE = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf', '#fb923c']
const pieOption = computed(() => {
  const cats = stats.value.category || []
  return {
    tooltip: { trigger: 'item', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
    legend: { bottom: 0, textStyle: { color: '#9ca3af', fontSize: 11 }, itemWidth: 8, itemHeight: 8 },
    series: [
      {
        type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'],
        itemStyle: { borderColor: '#1e1e1e', borderWidth: 2 },
        label: { color: '#9ca3af', fontSize: 11, formatter: '{b} {d}%' },
        data: cats.length
          ? cats.map((c, i) => ({
              name: c.name, value: c.value,
              itemStyle: { color: PALETTE[i % PALETTE.length], shadowColor: PALETTE[i % PALETTE.length] + '88', shadowBlur: 10 },
            }))
          : [{ name: '暂无事项', value: 1, itemStyle: { color: '#374151' } }],
      },
    ],
  }
})

/* 新建 / 编辑事项 */
const showAdd = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = ref(blankForm())
function blankForm() {
  return { title: '', priority: 'high', category: '考研', dueTs: null, description: '', estimate_minutes: 0 }
}
const priorityOptions = [
  { label: '高优先', value: 'high' }, { label: '中优先', value: 'medium' }, { label: '低优先', value: 'low' },
]
const categoryOptions = computed(() => {
  const base = ['考研', '课程', '知识整理', '生活', '学习']
  const extra = (stats.value.category || []).map((c) => c.name)
  return [...new Set([...base, ...extra])].map((c) => ({ label: c, value: c }))
})

function openNew() {
  editingId.value = null
  form.value = blankForm()
  showAdd.value = true
}
function openEdit(n) {
  editingId.value = n.id
  form.value = {
    title: n.title, priority: n.priority, category: n.category,
    dueTs: n.due ? new Date(n.due).getTime() : null,
    description: n.description || '', estimate_minutes: n.estimate_minutes || 0,
  }
  showAdd.value = true
}

async function submit() {
  if (!form.value.title.trim()) { message.warning('请填写标题'); return }
  const due = form.value.dueTs
    ? new Date(form.value.dueTs)
    : (() => { const d = new Date(); d.setHours(23, 59, 0, 0); return d })()
  const iso = `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, '0')}-${String(due.getDate()).padStart(2, '0')}T${String(due.getHours()).padStart(2, '0')}:${String(due.getMinutes()).padStart(2, '0')}:00`
  const payload = {
    title: form.value.title.trim(), priority: form.value.priority,
    category: form.value.category, due_at: iso,
    description: form.value.description.trim() || null,
    estimate_minutes: Number(form.value.estimate_minutes) || 0,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await store.updateNote(editingId.value, payload)
      message.success('事项已更新')
    } else {
      await store.addNote(payload)
      message.success('已创建，并同步总览 DDL 卡片')
    }
    showAdd.value = false
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    saving.value = false
  }
}

async function removeNote(n) {
  try {
    await store.removeNote(n.id)
    message.success(`已删除「${n.title}」`)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* 子任务展开 */
const expanded = ref(new Set())
function toggleExpand(id) {
  const s = new Set(expanded.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expanded.value = s
}
const subInput = ref({})
async function addSubtask(n) {
  const text = (subInput.value[n.id] || '').trim()
  if (!text) return
  try {
    await store.addSubtask(n.id, text)
    subInput.value[n.id] = ''
    message.success('子任务已添加')
  } catch (err) {
    message.error('添加失败：' + err.message)
  }
}
async function toggleSubtask(sub) {
  try { await store.toggleSubtask(sub.id, !sub.is_done) }
  catch (err) { message.error(err.message) }
}
async function removeSubtask(sub) {
  try { await store.removeSubtask(sub.id) }
  catch (err) { message.error(err.message) }
}

function toneOf(n) {
  if (n.status === 'done') return 'gray'
  if (!n.due) return 'green'
  const cd = countdown(n.due, now.value)
  if (cd.overdue) return 'red'
  const mins = (new Date(n.due).getTime() - now.value) / 60000
  return mins < 180 ? 'yellow' : 'green'
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>事项备忘</h2>
      <span class="spacer" />
      <NButton size="small" type="primary" @click="openNew">＋ 新建事项</NButton>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ stats.pending }}</div>
        <div class="label-3">待推进事项</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">{{ stats.todayDue }}</div>
        <div class="label-3">今日到期</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big">{{ stats.weekDone }}</div>
        <div class="label-3">本周已完成</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#f87171; text-shadow:0 0 14px #f8717166">{{ stats.overdue }}</div>
        <div class="label-3">已逾期</div>
      </div>
    </div>

    <div class="grid">
      <section class="col-7 card">
        <header class="card-head">
          <div class="card-title">☑ 事项清单 <span class="en">TASK LIST</span></div>
          <div class="filters">
            <button
              v-for="f in filters" :key="f.key"
              class="f-btn" :class="{ on: filter === f.key }"
              @click="filter = f.key"
            >{{ f.label }}</button>
          </div>
        </header>

        <div class="task-list">
          <template v-for="n in list" :key="n.id">
            <div class="task" :class="{ done: n.status === 'done' }">
              <button class="check" :class="{ on: n.status === 'done' }" @click="store.toggleNote(n.id)">
                {{ n.status === 'done' ? '✓' : '' }}
              </button>
              <div class="t-mid">
                <div class="t-title">{{ n.title }}</div>
                <div class="t-meta">
                  <span class="dot" :class="`dot-${toneOf(n)}`" />
                  <span class="chip" :class="`chip-${PRIORITY_TONE[n.priority]}`">{{ PRIORITY_LABEL[n.priority] }}优先</span>
                  <span class="chip">{{ n.category }}</span>
                  <span v-if="n.due" class="mono t-due">{{ n.due.slice(5, 16).replace('T', ' ') }}</span>
                  <span v-if="n.subtaskTotal" class="chip chip-blue mono">子任务 {{ n.subtaskDone }}/{{ n.subtaskTotal }}</span>
                  <button v-if="n.subtaskTotal || expanded.has(n.id)" class="sub-toggle" @click="toggleExpand(n.id)">
                    {{ expanded.has(n.id) ? '收起 ▴' : '展开子任务 ▾' }}
                  </button>
                </div>
              </div>
              <div class="t-cd mono" :class="{ red: n.due && countdown(n.due, now).overdue && n.status !== 'done' }">
                {{ n.status === 'done' ? '已完成' : n.due ? countdown(n.due, now).text : '无截止' }}
              </div>
              <div class="t-ops">
                <NButton size="tiny" quaternary @click="openEdit(n)">✎</NButton>
                <NPopconfirm @positive-click="removeNote(n)">
                  <template #trigger><NButton size="tiny" quaternary type="error">✕</NButton></template>
                  删除「{{ n.title }}」？子任务一并删除。
                </NPopconfirm>
              </div>
            </div>
            <div v-if="expanded.has(n.id)" class="sub-panel">
              <div v-for="s in n.subtasks" :key="s.id" class="sub-row">
                <button class="check sm" :class="{ on: s.is_done }" @click="toggleSubtask(s)">{{ s.is_done ? '✓' : '' }}</button>
                <span class="sub-title" :class="{ done: s.is_done }">{{ s.title }}</span>
                <button class="sub-del" @click="removeSubtask(s)">✕</button>
              </div>
              <div class="sub-add">
                <NInput v-model:value="subInput[n.id]" size="tiny" placeholder="添加子任务，回车提交"
                        @keyup.enter="addSubtask(n)">
                  <template #suffix>
                    <button class="sub-add-btn" @click="addSubtask(n)">＋</button>
                  </template>
                </NInput>
              </div>
            </div>
          </template>
          <div v-if="!list.length" class="empty">该筛选下没有事项 ✦</div>
        </div>
      </section>

      <div class="col-5" style="display:flex; flex-direction:column; gap:16px">
        <section class="card">
          <header class="card-head"><div class="card-title">◱ 推进趋势 <span class="en">7 DAYS</span></div></header>
          <GlowChart :option="trendOption" height="208px" />
        </section>
        <section class="card">
          <header class="card-head"><div class="card-title">◔ 分类占比 <span class="en">BY CATEGORY</span></div></header>
          <GlowChart :option="pieOption" height="228px" />
        </section>
      </div>
    </div>

    <NModal v-model:show="showAdd" preset="card" :title="editingId ? '编辑事项' : '新建待办事项'" style="width: 460px" :bordered="false">
      <div class="form">
        <div class="field">
          <label class="label-3">事项标题</label>
          <NInput v-model:value="form.title" placeholder="例如：完成 408 真题第二遍第 3 章" />
        </div>
        <div class="two">
          <div class="field">
            <label class="label-3">优先级</label>
            <NSelect v-model:value="form.priority" :options="priorityOptions" />
          </div>
          <div class="field">
            <label class="label-3">分类</label>
            <NSelect v-model:value="form.category" :options="categoryOptions" tag filterable />
          </div>
        </div>
        <div class="two">
          <div class="field">
            <label class="label-3">截止时间</label>
            <NDatePicker v-model:value="form.dueTs" type="datetime" clearable style="width: 100%"
                         placeholder="默认今天 23:59" />
          </div>
          <div class="field">
            <label class="label-3">预计耗时（分钟）</label>
            <NInputNumber v-model:value="form.estimate_minutes" :min="0" :max="1440" :step="15" style="width: 100%" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">描述（可选）</label>
          <NInput v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
                  placeholder="补充说明、参考资料等" />
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showAdd = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="submit">{{ editingId ? '保存修改' : '创建' }}</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }

.filters { display: flex; gap: 4px; }
.f-btn {
  font-size: 11px; padding: 3px 10px; border-radius: 999px; cursor: pointer;
  background: transparent; border: 1px solid var(--border); color: var(--text-2);
}
.f-btn.on { color: var(--accent); border-color: rgba(74, 222, 128, 0.5); background: rgba(74, 222, 128, 0.09); }

.task-list { display: flex; flex-direction: column; }
.task { display: flex; align-items: center; gap: 12px; padding: 10px 2px; border-bottom: 1px dashed var(--border); }
.task:last-child { border-bottom: none; }
.task.done { opacity: 0.45; }
.task.done .t-title { text-decoration: line-through; }
.check {
  width: 20px; height: 20px; border-radius: 6px; cursor: pointer; flex-shrink: 0;
  border: 1px solid var(--border); background: transparent; color: var(--accent); font-size: 12px;
}
.check:hover { border-color: rgba(74, 222, 128, 0.6); }
.check.on { background: var(--accent); border-color: var(--accent); color: #05130a; font-weight: 700; }
.t-mid { flex: 1; min-width: 0; }
.t-title { font-size: 13px; }
.t-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.t-due { font-size: 10px; color: var(--text-3); }
.t-cd { font-size: 12px; color: var(--accent); flex-shrink: 0; }
.t-cd.red { color: var(--red); }
.empty { color: var(--text-3); font-size: 12px; text-align: center; padding: 20px 0; }

.form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }

/* 操作与子任务 */
.t-ops { display: flex; gap: 2px; flex-shrink: 0; }
.sub-toggle {
  all: unset; cursor: pointer; font-size: 10px; color: var(--text-3);
  padding: 1px 8px; border-radius: 999px; border: 1px dashed var(--border);
}
.sub-toggle:hover { color: var(--accent); border-color: rgba(74,222,128,0.4); }
.sub-panel { margin: -2px 0 8px 34px; padding: 6px 10px; border-left: 2px solid var(--border); }
.sub-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.sub-title { flex: 1; font-size: 12px; color: var(--text-2); }
.sub-title.done { text-decoration: line-through; opacity: 0.5; }
.sub-del { all: unset; cursor: pointer; font-size: 10px; color: var(--text-3); padding: 1px 5px; border-radius: 4px; }
.sub-del:hover { color: #f87171; background: rgba(248,113,113,0.12); }
.sub-add { margin-top: 4px; }
.sub-add-btn { all: unset; cursor: pointer; color: var(--text-3); font-size: 13px; }
.sub-add-btn:hover { color: var(--accent); }
.check.sm { width: 16px; height: 16px; font-size: 10px; border-radius: 5px; }
</style>
