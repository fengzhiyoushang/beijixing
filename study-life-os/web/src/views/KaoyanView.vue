<script setup>
import { marked } from 'marked'
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { kaoyanApi } from '../api'
import { todayStr } from '../utils/format'

const message = useMessage()

const goal = ref(null)
const subRows = ref([])
const phases = ref([])
const progress = ref(null)
const analysis = ref(null)
const reviewRes = ref(null)
const showReview = ref(false)

const dateSel = ref(todayStr())
const daily = ref([])
const newTask = reactive({ title: '', subject: '', minutes: 60 })

const gform = reactive({ target_school: '', target_major: '', target_year: null, exam_date: null, status: 'active' })

async function loadAll() {
  goal.value = await kaoyanApi.goal()
  if (goal.value) {
    Object.assign(gform, {
      target_school: goal.value.target_school, target_major: goal.value.target_major,
      target_year: goal.value.target_year, exam_date: goal.value.exam_date,
    })
    const subs = goal.value.detail?.subjects || {}
    subRows.value = Object.entries(subs).map(([name, s]) => ({ name, ...s }))
    phases.value = goal.value.phases || []
  } else {
    subRows.value = []
    phases.value = []
  }
  progress.value = await kaoyanApi.progress()
  loadDaily()
}

function addSubRow() { subRows.value.push({ name: '新科目', target: 100, current: 60, max: 100 }) }

async function saveGoal() {
  const detail = { subjects: {} }
  let tt = 0, tc = 0
  for (const r of subRows.value) {
    if (!r.name) continue
    detail.subjects[r.name] = { target: Number(r.target) || 0, current: Number(r.current) || 0, max: Number(r.max) || 100 }
    tt += Number(r.target) || 0
    tc += Number(r.current) || 0
  }
  goal.value = await kaoyanApi.saveGoal({
    target_school: gform.target_school, target_major: gform.target_major || null,
    target_year: gform.target_year || null, exam_date: gform.exam_date || null,
    total_target: tt, total_current: tc, detail,
  })
  message.success('目标已保存')
  loadAll()
}

const gap = computed(() => (goal.value ? goal.value.total_target - goal.value.total_current : 0))

async function runGap() {
  analysis.value = await kaoyanApi.gapAnalysis()
}
async function runPlan() {
  const rep = await kaoyanApi.generatePlan({ auto_daily: true, daily_days: 3 })
  message.success(`已生成 ${rep.phases.length} 个阶段 + ${rep.daily_tasks_created} 项每日任务`)
  loadAll()
}
async function runReview() {
  reviewRes.value = await kaoyanApi.review(7)
  showReview.value = true
}

async function loadDaily() {
  const d = await kaoyanApi.dailyTasks(dateSel.value)
  daily.value = d.tasks
}
async function toggleTask(t, checked) {
  await kaoyanApi.patchPlanTask(t.id, { done: checked, done_minutes: checked ? t.planned_minutes : null })
  loadDaily(); loadAll()
}
async function addTask() {
  if (!newTask.title.trim()) return
  await kaoyanApi.addDailyTask({ date: dateSel.value, title: newTask.title, subject: newTask.subject || null, planned_minutes: Number(newTask.minutes) || 60 })
  newTask.title = ''; newTask.subject = ''
  loadDaily()
}
async function deletePhase(p) {
  await kaoyanApi.deletePhase(p.id)
  loadAll()
}

onMounted(loadAll)
const md = (s) => marked.parse(s || '')
</script>

<template>
  <div class="page">
    <n-grid :cols="4" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
      <!-- 目标卡 -->
      <n-gi span="0:4 1300:2">
        <n-card size="small" title="◎ 考研目标">
          <n-form :show-label="false" size="small">
            <n-grid :cols="3" :x-gap="8">
              <n-gi><n-input v-model:value="gform.target_school" placeholder="目标院校" /></n-gi>
              <n-gi><n-input v-model:value="gform.target_major" placeholder="专业" /></n-gi>
              <n-gi><n-date-picker v-model:formatted-value="gform.exam_date" type="date" value-format="yyyy-MM-dd" style="width: 100%" placeholder="考试日期" /></n-gi>
            </n-grid>
          </n-form>
          <div class="section-title" style="margin-top: 12px">各科分数模型（目标分 / 当前预估分）</div>
          <table class="sub-table">
            <thead><tr><th>科目</th><th>满分</th><th>目标</th><th>当前</th><th>缺口</th><th>达成率</th><th /></tr></thead>
            <tbody>
              <tr v-for="(r, i) in subRows" :key="i">
                <td><input v-model="r.name" class="cell-input" /></td>
                <td><input v-model.number="r.max" type="number" class="cell-input" /></td>
                <td><input v-model.number="r.target" type="number" class="cell-input" /></td>
                <td><input v-model.number="r.current" type="number" class="cell-input" /></td>
                <td class="mono gap-cell">{{ (r.target - r.current) }}</td>
                <td>
                  <n-progress type="line" :percentage="Math.min(100, Math.round((r.current / Math.max(r.target, 1)) * 100))" :height="5" :show-indicator="false" />
                </td>
                <td><n-button size="tiny" quaternary type="error" @click="subRows.splice(i, 1)">✕</n-button></td>
              </tr>
            </tbody>
          </table>
          <n-space style="margin-top: 10px">
            <n-button size="tiny" dashed @click="addSubRow">＋ 科目</n-button>
            <n-button size="small" type="primary" @click="saveGoal">保存目标</n-button>
            <n-button v-if="goal" size="small" @click="runGap">差距分析</n-button>
            <n-button v-if="goal" size="small" type="info" @click="runPlan">生成阶段规划</n-button>
            <n-button v-if="goal" size="small" @click="runReview">AI 周复盘</n-button>
          </n-space>
        </n-card>
      </n-gi>

      <!-- 进度总览 -->
      <n-gi span="0:4 1300:2">
        <n-card size="small" title="▮ 进度复盘">
          <div v-if="progress" class="prog-grid">
            <div class="pg-item"><div class="k mono">剩余天数</div><div class="stat-num" style="font-size:22px">{{ progress.days_left }}</div></div>
            <div class="pg-item"><div class="k mono">分数差距</div><div class="stat-num" style="font-size:22px;color:#fbbf24">{{ progress.gap }}</div></div>
            <div class="pg-item"><div class="k mono">当前/目标分</div><div class="stat-num" style="font-size:22px">{{ progress.total_current }}/{{ progress.total_target }}</div></div>
            <div class="pg-item"><div class="k mono">每日任务完成率</div><div class="stat-num" style="font-size:22px">{{ progress.daily_task_done_rate != null ? Math.round(progress.daily_task_done_rate * 100) + '%' : '—' }}</div></div>
          </div>
          <div v-if="progress" style="margin-top: 8px">
            <div class="k mono" style="font-size:11px;color:#5b7290">分数达成</div>
            <n-progress type="line" :percentage="Math.round(progress.score_rate * 100)" indicator-placement="inside" />
          </div>
          <div v-if="analysis" class="analysis">
            <div class="section-title">✂ 差距分析</div>
            <table class="sub-table">
              <thead><tr><th>科目</th><th>目标</th><th>当前</th><th>缺口</th><th>达成率</th></tr></thead>
              <tbody>
                <tr v-for="s in analysis.numeric.subjects" :key="s.subject">
                  <td>{{ s.subject }}</td><td class="mono">{{ s.target }}</td><td class="mono">{{ s.current }}</td>
                  <td class="mono" style="color:#ff5c7a">-{{ s.gap }}</td>
                  <td class="mono">{{ Math.round(s.reach_rate * 100) }}%</td>
                </tr>
              </tbody>
            </table>
            <div v-if="analysis.ai_report" class="md-body ai-md" v-html="md(analysis.ai_report)" />
            <div v-else class="mono rule">{{ analysis.rule_summary }}<br>（配置 DEEPSEEK_API_KEY 可获得模型诊断报告）</div>
          </div>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 阶段 -->
    <div class="section-title" style="margin-top: 16px">— 阶段规划 PHASES —</div>
    <n-empty v-if="goal && !phases.length" description="点击「生成阶段规划」创建" size="small" />
    <n-grid :cols="3" :x-gap="12" responsive="screen" item-responsive>
      <n-gi v-for="p in phases" :key="p.id" span="0:3 1000:1">
        <n-card size="small" :class="['phase', { active: p.status === 'active' }]">
          <div class="ph-head">
            <span class="ph-name">{{ p.name }}</span>
            <n-tag size="tiny" :bordered="false" :type="p.status === 'active' ? 'success' : p.status === 'done' ? 'default' : 'info'">{{ p.status }}</n-tag>
            <n-button size="tiny" quaternary type="error" @click="deletePhase(p)">✕</n-button>
          </div>
          <div class="ph-date mono">{{ (p.start_date || '').slice(5) }} → {{ (p.end_date || '').slice(5) }}</div>
          <div class="ph-obj">{{ p.objective }}</div>
          <n-progress type="line" :height="4" :percentage="p.task_total ? Math.round((p.task_done / p.task_total) * 100) : 0" :show-indicator="false" />
          <div class="ph-foot mono">任务 {{ p.task_done }}/{{ p.task_total }}</div>
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 每日任务 -->
    <div class="section-title" style="margin-top: 16px">— 每日任务拆解 DAILY —</div>
    <n-card size="small">
      <n-space align="center" :size="10" style="margin-bottom: 8px">
        <n-date-picker v-model:formatted-value="dateSel" type="date" value-format="yyyy-MM-dd" size="small" style="width: 140px" @update:formatted-value="loadDaily" />
        <n-input v-model:value="newTask.title" size="small" placeholder="新任务标题" style="width: 200px" @keyup.enter="addTask" />
        <n-input v-model:value="newTask.subject" size="small" placeholder="科目" style="width: 90px" />
        <n-input-number v-model:value="newTask.minutes" size="small" style="width: 100px" :min="5" :step="5" />
        <span class="mono" style="color:#5b7290;font-size:11px">min</span>
        <n-button size="small" type="primary" @click="addTask">添加</n-button>
      </n-space>
      <div v-if="!daily.length" class="empty mono">// 当日无拆解任务</div>
      <div v-for="t in daily" :key="t.id" class="dt-row">
        <n-checkbox :checked="t.done" @update:checked="(v) => toggleTask(t, v)" />
        <span class="dt-title" :class="{ done: t.done }">{{ t.title }}</span>
        <span class="dt-sub mono">{{ t.subject }} · {{ t.planned_minutes }}min</span>
        <n-button size="tiny" quaternary type="error" @click="kaoyanApi.deletePlanTask(t.id).then(loadDaily)">✕</n-button>
      </div>
    </n-card>

    <n-modal v-model:show="showReview" preset="card" title="AI 周复盘" style="width: 560px">
      <div v-if="reviewRes">
        <div class="mono rule" style="margin-bottom: 8px">{{ reviewRes.rule_report }}</div>
        <div v-if="reviewRes.ai_report" class="md-body" v-html="md(reviewRes.ai_report)" />
        <div v-else class="empty mono">// 配置 DeepSeek Key 后解锁 AI 复盘点评</div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.phase { border-left: 3px solid rgba(56,189,248,0.3); }
.phase.active { border-left-color: #00e5a0; box-shadow: 0 0 18px rgba(0,229,160,0.12); }
.ph-head { display: flex; align-items: center; gap: 8px; }
.ph-name { font-weight: 700; color: #e6f1ff; flex: 1; }
.ph-date { font-size: 11px; color: #5b7290; margin: 4px 0; }
.ph-obj { font-size: 12px; color: #9fb8ce; line-height: 1.6; min-height: 44px; }
.ph-foot { font-size: 10px; color: #46596f; margin-top: 6px; }
.prog-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.pg-item .k { font-size: 10px; color: #5b7290; margin-bottom: 4px; }
.sub-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sub-table th { text-align: left; color: #5b7290; font-weight: 400; font-size: 11px; padding: 4px; border-bottom: 1px solid rgba(56,189,248,0.15); }
.sub-table td { padding: 3px 4px; border-bottom: 1px dashed rgba(56,189,248,0.08); color: #c9d6e8; }
.cell-input { background: rgba(10,16,28,0.8); border: 1px solid rgba(56,189,248,0.2); color: #dce8f7; border-radius: 4px; width: 100%; padding: 2px 6px; font-size: 12px; }
.gap-cell { color: #ff8ba0; }
.analysis { margin-top: 14px; }
.ai-md { margin-top: 10px; padding: 10px; background: rgba(0,229,160,0.05); border: 1px dashed rgba(0,229,160,0.3); border-radius: 8px; }
.rule { font-size: 12px; color: #9fb8ce; white-space: pre-line; }
.dt-row { display: flex; align-items: center; gap: 10px; padding: 7px 4px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.dt-title { flex: 1; font-size: 13px; }
.dt-title.done { text-decoration: line-through; color: #4a617f; }
.dt-sub { font-size: 11px; color: #5b7290; }
.empty { color: #4a617f; font-size: 12px; padding: 10px 2px; }
</style>
