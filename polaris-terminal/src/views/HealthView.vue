<script setup>
import { computed, ref } from 'vue'
import { NButton, NInput, NInputNumber, NModal, NPopconfirm, NSelect, NSlider, NSwitch, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'

const message = useMessage()
const h = computed(() => store.health)

const form = ref({ kind: '饮水', value: '', note: '' })
const kindOptions = [
  { label: '饮水（ml）', value: '饮水' },
  { label: '运动（分钟）', value: '运动' },
  { label: '步数', value: '步数' },
  { label: '睡眠（小时）', value: '睡眠' },
  { label: '体重（kg）', value: '体重' },
  { label: '起身活动', value: '起身活动' },
  { label: '其他', value: '其他' },
]
const valueHint = computed(() => ({
  饮水: '如 500', 运动: '如 45', 步数: '如 6000', 睡眠: '如 7.5', 体重: '如 62.5',
}[form.value.kind] || '备注（可选）'))

const sleepOption = computed(() => ({
  grid: { left: 34, right: 16, top: 26, bottom: 24 },
  legend: { data: ['睡眠时长', '运动时长'], textStyle: { color: '#9ca3af', fontSize: 11 }, top: 0, right: 0 },
  xAxis: { type: 'category', data: h.value.weekSleep.days.map((d) => d.slice(3)), ...axisBase(), splitLine: { show: false } },
  yAxis: { type: 'value', name: '小时 / 分钟', nameTextStyle: { color: '#6b7280', fontSize: 10 }, ...axisBase() },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    { name: '睡眠时长', ...glowBar('#c084fc'), data: h.value.weekSleep.hours, barWidth: '30%' },
    { name: '运动时长', ...glowLine(store.settings.accent), data: h.value.exerciseWeek },
  ],
}))

const waterRate = computed(() => Math.min(100, Math.round((h.value.waterToday / h.value.waterTarget) * 100)))
const avgSleep = computed(() => {
  const arr = h.value.weekSleep.hours
  return arr.length ? (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1) : '0.0'
})

function numVal(raw) {
  const n = parseFloat(String(raw).replace(/[^\d.]/g, ''))
  return isNaN(n) ? 0 : n
}

/** 写入真实健康记录（后端按日期 upsert，运动/饮水/步数自动累加） */
const savingLog = ref(false)
async function addLog() {
  if (!form.value.value && form.value.kind !== '其他' && form.value.kind !== '起身活动') {
    message.warning('请填写数值'); return
  }
  const payload = { date: new Date().toISOString().slice(0, 10) }
  const n = numVal(form.value.value)
  if (form.value.kind === '饮水') payload.water_ml = n
  else if (form.value.kind === '运动') payload.exercise_minutes = n
  else if (form.value.kind === '步数') payload.steps = n
  else if (form.value.kind === '睡眠') payload.sleep_minutes = Math.round(n * 60)
  else if (form.value.kind === '体重') payload.weight = n
  else if (form.value.kind === '起身活动') payload.sedentary_minutes = 0
  if (form.value.note) payload.note = form.value.note

  savingLog.value = true
  try {
    await store.addHealthRecord(payload)
    await store.addNews('green', '健康', `已记录：${form.value.kind} ${form.value.value}`)
    message.success('健康记录已写入后端，并同步快讯')
    form.value = { kind: form.value.kind, value: '', note: '' }
  } catch (err) {
    message.error(err.message)
  } finally {
    savingLog.value = false
  }
}

/** 起身：重置后端久坐计时 */
async function takeBreak() {
  try {
    await store.takeSedentaryBreak()
    h.value.sedentary.todayBreaks = (h.value.sedentary.todayBreaks || 0) + 1
    await store.addNews('green', '健康', '完成一次起身活动 ✓ 久坐计时已重置')
    message.success('已重置久坐计时 ✦')
  } catch (err) {
    message.error(err.message)
  }
}

/* ── 久坐设置持久化 ── */
const savingSet = ref(false)
async function saveInterval(v) {
  savingSet.value = true
  try {
    await store.saveHealthSettings({ sedentary_interval_min: v })
    message.success(`提醒间隔已保存：${v} 分钟`)
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingSet.value = false
  }
}
async function toggleEnabled(on) {
  try {
    await store.saveHealthSettings({ sedentary_enabled: on })
    message.success(on ? '久坐提醒已开启' : '久坐提醒已关闭')
  } catch (err) {
    store.health.sedentaryEnabled = !on
    message.error('保存失败：' + err.message)
  }
}
if (store.health.sedentaryEnabled === undefined) store.health.sedentaryEnabled = true

/* ── 记录编辑 / 删除 ── */
const showEdit = ref(false)
const editing = ref(null)
const rf = ref({ sleep_hours: null, exercise_minutes: null, water_ml: null, weight: null, steps: null, mood: null, note: '' })
const moodOptions = [
  { label: '1 · 很差', value: 1 }, { label: '2 · 较差', value: 2 }, { label: '3 · 一般', value: 3 },
  { label: '4 · 良好', value: 4 }, { label: '5 · 很棒', value: 5 },
]
function openEdit(l) {
  editing.value = l
  rf.value = {
    sleep_hours: l.sleep_hours || null, exercise_minutes: l.exercise_minutes ?? null,
    water_ml: l.water_ml ?? null, weight: l.weight, steps: l.steps ?? null,
    mood: l.mood, note: l.note || '',
  }
  showEdit.value = true
}
async function saveEdit() {
  savingLog.value = true
  try {
    const payload = {
      sleep_minutes: rf.value.sleep_hours ? Math.round(Number(rf.value.sleep_hours) * 60) : 0,
      exercise_minutes: Number(rf.value.exercise_minutes) || 0,
      water_ml: Number(rf.value.water_ml) || 0,
      steps: Number(rf.value.steps) || 0,
      weight: rf.value.weight === null || rf.value.weight === '' ? null : Number(rf.value.weight),
      mood: rf.value.mood,
      note: rf.value.note.trim() || null,
    }
    await store.updateHealthRecord(editing.value.id, payload)
    message.success(`${editing.value.date} 的记录已更新`)
    showEdit.value = false
  } catch (err) {
    message.error('更新失败：' + err.message)
  } finally {
    savingLog.value = false
  }
}
async function removeLog(l) {
  try {
    await store.removeHealthRecord(l.id)
    message.success(`已删除 ${l.date} 的记录`)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 真实建议（后端 report.tips 按关键字映射色调） ── */
function tipTone(t) {
  if (t.includes('睡眠')) return 'blue'
  if (t.includes('久坐') || t.includes('起身')) return 'red'
  if (t.includes('饮水')) return 'yellow'
  if (t.includes('运动')) return 'green'
  return 'green'
}
function tipTitle(t) {
  const key = ['睡眠', '运动', '久坐', '饮水', '体重']
  const hit = key.find((w) => t.includes(w))
  return hit ? `${hit}建议` : '健康提示'
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>健康管理</h2>
      <span class="spacer" />
      <span class="chip chip-accent">连续打卡 {{ h.checkinStreak }} 天</span>
    </div>

    <div v-if="h.sedentary.shouldBreak" class="alert">
      <span class="dot dot-red" />
      <div class="a-mid">
        <div class="a-title">⚠ 久坐提醒：已连续 {{ h.sedentary.minutes }} 分钟未起身</div>
        <div class="a-sub mono">阈值 {{ h.sedentary.interval }} 分钟 · 今日已起身 {{ h.sedentary.todayBreaks }} 次 · 免打扰时段 {{ h.sedentary.quiet }}</div>
      </div>
      <NButton size="small" type="primary" @click="takeBreak">我起身了 ✓</NButton>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big" :style="{ color: h.sedentary.shouldBreak ? '#f87171' : '#4ade80' }">{{ h.sedentary.minutes }}m</div>
        <div class="label-3">当前连续久坐</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#c084fc; text-shadow:0 0 14px #c084fc66">{{ h.lastSleep.hours }}h</div>
        <div class="label-3">昨夜睡眠（{{ h.lastSleep.bed }} → {{ h.lastSleep.up }}）</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ h.waterToday }}ml</div>
        <div class="label-3">今日饮水（目标 {{ h.waterTarget }}ml）</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">{{ avgSleep }}h</div>
        <div class="label-3">7 日平均睡眠</div>
      </div>
    </div>

    <div class="grid">
      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">◱ 作息与运动趋势 <span class="en">7-DAY REPORT</span></div>
          <span class="chip chip-blue">饮水完成度 {{ waterRate }}%</span>
        </header>
        <GlowChart :option="sleepOption" height="248px" />
        <div class="water-bar">
          <div class="w-track"><div class="w-fill" :style="{ width: waterRate + '%' }" /></div>
          <span class="mono label-3">今日饮水 {{ h.waterToday }} / {{ h.waterTarget }} ml</span>
        </div>
      </section>

      <section class="col-4 card">
        <header class="card-head"><div class="card-title">✎ 快速记录 <span class="en">QUICK LOG</span></div></header>
        <div class="log-form">
          <NSelect v-model:value="form.kind" size="small" :options="kindOptions" />
          <NInput v-model:value="form.value" size="small" :placeholder="valueHint" />
          <NInput v-model:value="form.note" size="small" placeholder="备注（可选）" @keyup.enter="addLog" />
          <NButton size="small" type="primary" block :loading="savingLog" @click="addLog">写入记录</NButton>
        </div>
        <div class="log-list">
          <div v-for="l in h.logs" :key="l.id" class="log-row">
            <span class="mono l-time">{{ l.time }}</span>
            <span class="chip chip-accent">{{ l.kind }}</span>
            <span class="mono l-val">{{ l.value || '—' }}</span>
            <span class="l-note c3">{{ l.note || '' }}</span>
            <button class="op-btn" title="编辑该日记录" @click="openEdit(l)">✎</button>
            <NPopconfirm @positive-click="removeLog(l)">
              <template #trigger><button class="op-btn del" title="删除该日记录">✕</button></template>
              删除 {{ l.date }} 的健康记录？
            </NPopconfirm>
          </div>
          <div v-if="!h.logs.length" class="empty-log mono">暂无记录 · 在上方写入今日数据</div>
        </div>
      </section>

      <section class="col-5 card">
        <header class="card-head"><div class="card-title">⚙ 久坐提醒设置 <span class="en">SEDENTARY</span></div></header>
        <div class="set-row">
          <span class="label-3">启用提醒</span>
          <NSwitch v-model:value="h.sedentaryEnabled" size="small" @update:value="toggleEnabled" />
          <span class="mono s-val">{{ h.sedentaryEnabled ? '开' : '关' }}</span>
        </div>
        <div class="set-row">
          <span class="label-3">提醒间隔</span>
          <NSlider v-model:value="h.sedentary.interval" :min="20" :max="120" :step="5" :disabled="savingSet" style="width: 190px" @change="saveInterval" />
          <span class="mono s-val">{{ h.sedentary.interval }} 分钟</span>
        </div>
        <div class="set-row">
          <span class="label-3">今日起身次数</span>
          <span class="mono s-val">{{ h.sedentary.todayBreaks }} 次</span>
          <NButton size="tiny" type="primary" ghost @click="takeBreak">模拟起身</NButton>
        </div>
        <div class="set-row">
          <span class="label-3">免打扰时段</span>
          <span class="mono s-val">{{ h.sedentary.quiet }}</span>
        </div>
        <div class="set-tip mono">
          间隔与开关已持久化到后端（PUT /health/settings），Web 与小程序共享同一份设置；Web 端页面常驻时由心跳检测触发提醒。
        </div>
      </section>

      <section class="col-7 card">
        <header class="card-head"><div class="card-title">♥ 健康建议 <span class="en">INSIGHTS</span></div></header>
        <div class="insight-list">
          <div v-for="(t, i) in h.tips" :key="i" class="insight">
            <span class="dot" :class="`dot-${tipTone(t)}`" />
            <div><b>{{ tipTitle(t) }}</b>：{{ t }}</div>
          </div>
        </div>
      </section>
    </div>

    <!-- 记录编辑弹窗 -->
    <NModal v-model:show="showEdit" preset="card" :title="`✎ 编辑 ${editing ? editing.date : ''} 的健康记录`"
            style="width: 460px" :bordered="false">
      <div class="edit-form">
        <div class="two">
          <div class="field">
            <label class="label-3">睡眠（小时）</label>
            <NInputNumber v-model:value="rf.sleep_hours" :min="0" :max="24" :step="0.5" style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">运动（分钟）</label>
            <NInputNumber v-model:value="rf.exercise_minutes" :min="0" :max="1440" :step="5" style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">饮水（ml）</label>
            <NInputNumber v-model:value="rf.water_ml" :min="0" :max="10000" :step="50" style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">步数</label>
            <NInputNumber v-model:value="rf.steps" :min="0" :max="200000" :step="100" style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">体重（kg，可空）</label>
            <NInputNumber v-model:value="rf.weight" :min="20" :max="300" :step="0.1" style="width: 100%" />
          </div>
          <div class="field">
            <label class="label-3">今日心情</label>
            <NSelect v-model:value="rf.mood" :options="moodOptions" clearable placeholder="可选" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">备注</label>
          <NInput v-model:value="rf.note" placeholder="如：晚睡 1 小时，状态一般" />
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showEdit = false">取消</NButton>
          <NButton type="primary" :loading="savingLog" @click="saveEdit">保存</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }

.alert {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
  background: rgba(248, 113, 113, 0.07); border: 1px solid rgba(248, 113, 113, 0.35);
  border-radius: var(--radius); padding: 12px 16px;
}
.a-mid { flex: 1; }
.a-title { font-size: 13px; color: #fca5a5; }
.a-sub { font-size: 10.5px; color: var(--text-3); margin-top: 3px; }

.water-bar { margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 10px; }
.w-track { height: 6px; border-radius: 3px; background: #262626; overflow: hidden; margin-bottom: 6px; }
.w-fill { height: 100%; background: #60a5fa; box-shadow: 0 0 10px #60a5fa; transition: width 0.3s ease; }

.log-form { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.log-list { border-top: 1px dashed var(--border); padding-top: 8px; max-height: 210px; overflow-y: auto; }
.log-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 11.5px; }
.l-time { color: var(--text-3); font-size: 10px; width: 38px; }
.l-val { color: var(--blue); width: 108px; flex-shrink: 0; }
.l-note { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c3 { color: var(--text-3); }
.empty-log { padding: 18px 0; text-align: center; font-size: 11px; color: var(--text-3); }

.op-btn {
  width: 22px; height: 22px; border-radius: 6px; cursor: pointer; flex-shrink: 0;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 10px;
}
.op-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.op-btn.del:hover { color: var(--red); border-color: rgba(248, 113, 113, 0.4); }

.set-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px dashed var(--border); }
.set-row .label-3 { width: 92px; }
.s-val { color: var(--text-2); font-size: 12px; }
.set-tip { font-size: 10px; color: var(--text-3); margin-top: 10px; }

.insight-list { display: flex; flex-direction: column; gap: 10px; }
.insight { display: flex; gap: 10px; font-size: 12.5px; color: var(--text-2); line-height: 1.7; }
.insight .dot { margin-top: 6px; }
.insight b { color: var(--text-1); }

.edit-form { display: flex; flex-direction: column; gap: 14px; }
.edit-form .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.edit-form .field { display: flex; flex-direction: column; gap: 6px; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
