<script setup>
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useMessage, useNotification } from 'naive-ui'
import { healthApi } from '../api'
import StatCard from '../components/StatCard.vue'
import { categoryAxis, mountChart, valueAxis } from '../utils/chart'

const message = useMessage()
const notification = useNotification()

const today = ref(null)
const report = ref(null)
const settings = ref(null)
const logForm = reactive({ kind: 'water', minutes: 30, value: 500, note: '' })
const sleepEl = ref(null)

const KIND_LABEL = { sleep: '睡眠', wake: '起床', water: '饮水', exercise: '运动', sedentary: '起身活动', other: '其他' }

async function loadAll() {
  today.value = await healthApi.today()
  report.value = await healthApi.report(7)
  settings.value = await healthApi.settings()
  requestAnimationFrame(renderCharts)
}

function renderCharts() {
  if (!report.value || !sleepEl.value) return
  const d = report.value.daily
  mountChart(sleepEl.value, {
    legend: { textStyle: { color: '#7d93b2', fontSize: 10 }, top: 0 },
    xAxis: categoryAxis(d.map((x) => x.date.slice(5))),
    yAxis: [valueAxis('min'), valueAxis('ml')],
    series: [
      { name: '睡眠(分钟)', type: 'bar', data: d.map((x) => x.sleep_minutes), itemStyle: { color: '#a78bfa', borderRadius: [3, 3, 0, 0] } },
      { name: '饮水(ml)', type: 'line', yAxisIndex: 1, smooth: true, data: d.map((x) => x.water_ml), itemStyle: { color: '#38bdf8' } },
      { name: '起身次数', type: 'line', smooth: true, data: d.map((x) => x.breaks), itemStyle: { color: '#00e5a0' } },
    ],
  })
}

async function saveSettings() {
  await healthApi.saveSettings(settings.value)
  message.success('设置已保存')
}

async function addLog() {
  const payload = { kind: logForm.kind, note: logForm.note || null }
  if (['sleep', 'exercise'].includes(logForm.kind)) payload.minutes = Number(logForm.minutes) || null
  if (logForm.kind === 'water') payload.value = Number(logForm.value) || null
  await healthApi.log(payload)
  logForm.note = ''
  message.success('已记录')
  loadAll()
}

async function takeBreak() {
  await healthApi.takeBreak()
  notification.success({ title: '做得好 ✦', content: '久坐计时已重置', duration: 2500 })
  loadAll()
}

// ── 久坐提醒心跳（60s）──
let hbTimer = null
async function heartbeat() {
  try {
    const st = await healthApi.heartbeat()
    if (st.should_break) {
      notification.warning({
        title: '⏸ 久坐提醒',
        content: st.message,
        duration: 8000,
        action: () => h('button', { class: 'link-btn', onClick: () => { takeBreak(); notification.destroyAll() } }, '已完成起身 ✓'),
      })
    }
    if (today.value) today.value.sedentary = st
  } catch { /* 静默 */ }
}
onMounted(() => {
  loadAll()
  heartbeat()
  hbTimer = setInterval(heartbeat, 60000)
})
onUnmounted(() => clearInterval(hbTimer))
</script>

<template>
  <div class="page">
    <n-space vertical :size="14">
      <n-grid :cols="5" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:2 1000:1"><StatCard label="昨夜睡眠" :value="report?.sleep.avg_minutes ? Math.floor(report.sleep.avg_minutes / 60) + 'h' + (report.sleep.avg_minutes % 60) + 'm' : '—'" sub="7日均值" color="#a78bfa" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="本周运动" :value="`${report?.exercise_minutes || 0}m`" sub="累计时长" color="#00e5a0" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="本周饮水" :value="`${Math.round((report?.water_total_ml || 0) / 100) / 10}L`" sub="累计" color="#38bdf8" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="起身活动" :value="`${report?.sedentary_breaks || 0}次`" sub="7天内" color="#f472b6" /></n-gi>
        <n-gi span="0:2 1000:1">
          <StatCard label="当前久坐状态" :value="today?.sedentary?.should_break ? '需起身!' : `${today?.sedentary?.minutes_since_break ?? '—'}m`" :sub="`间隔阈值 ${today?.sedentary?.interval_min ?? 45} 分钟`" :color="today?.sedentary?.should_break ? '#ff5c7a' : '#00e5a0'" />
        </n-gi>
      </n-grid>

      <n-alert v-if="today?.sedentary?.should_break" type="error" :bordered="false" title="⏸ 久坐提醒">
        {{ today.sedentary.message }}
        <n-button size="tiny" type="primary" style="margin-left: 12px" @click="takeBreak">我起身了 ✓</n-button>
      </n-alert>

      <n-grid :cols="6" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:6 1200:4">
          <n-card size="small" title="♥ 近 7 天作息 / 饮水 / 活动">
            <div ref="sleepEl" class="chart" style="height: 280px" />
          </n-card>
        </n-gi>
        <n-gi span="0:6 1200:2">
          <n-card size="small" title="✎ 快速记录">
            <n-space :size="8" align="center" style="margin-bottom: 10px">
              <n-select v-model:value="logForm.kind" size="small" style="width: 110px"
                :options="['sleep', 'water', 'exercise', 'other'].map((k) => ({ label: KIND_LABEL[k], value: k }))" />
              <n-input-number v-if="['sleep', 'exercise'].includes(logForm.kind)" v-model:value="logForm.minutes" size="small" style="width: 110px" :min="1">
              </n-input-number>
              <n-input-number v-if="logForm.kind === 'water'" v-model:value="logForm.value" size="small" style="width: 110px" :min="0" :step="100" />
              <span v-if="logForm.kind !== 'other'" class="mono unit">{{ logForm.kind === 'water' ? 'ml' : 'min' }}</span>
            </n-space>
            <n-input v-model:value="logForm.note" size="small" placeholder="备注（可选）" style="margin-bottom: 10px" @keyup.enter="addLog" />
            <n-button size="small" type="primary" block @click="addLog">记录</n-button>

            <div class="section-title" style="margin-top: 16px">今日记录</div>
            <div v-for="l in (today?.logs || [])" :key="l.id" class="log-row mono">
              <span class="lt">{{ (l.happened_at || '').slice(11, 16) }}</span>
              <span>{{ KIND_LABEL[l.kind] || l.kind }}</span>
              <span class="lv">{{ l.kind === 'water' ? (l.value || 0) + 'ml' : (l.minutes || 0) + 'min' }}</span>
              <span class="ln">{{ l.note }}</span>
            </div>
            <div v-if="!today?.logs?.length" class="empty mono">// 今天还没有健康记录</div>
          </n-card>
        </n-gi>
      </n-grid>

      <!-- 久坐设置 -->
      <n-card v-if="settings" size="small" title="⚙ 久坐与作息设置">
        <n-grid :cols="6" :x-gap="12">
          <n-gi span="0:3 1100:1">
            <n-form-item label="启用久坐提醒" size="small"><n-switch v-model:value="settings.sedentary_enabled" /></n-form-item>
          </n-gi>
          <n-gi span="0:3 1100:1">
            <n-form-item label="提醒间隔(分钟)" size="small"><n-input-number v-model:value="settings.sedentary_interval_min" :min="5" :max="240" style="width: 100%" /></n-form-item>
          </n-gi>
          <n-gi span="0:3 1100:2">
            <n-form-item label="免打扰时段" size="small">
              <n-space :size="6" align="center">
                <n-time-picker v-model:formatted-value="settings.quiet_start" format="HH:mm" value-format="HH:mm" size="small" style="width: 100px" />
                <span class="sep">→</span>
                <n-time-picker v-model:formatted-value="settings.quiet_end" format="HH:mm" value-format="HH:mm" size="small" style="width: 100px" />
              </n-space>
            </n-form-item>
          </n-gi>
          <n-gi span="0:3 1100:2">
            <n-form-item label="活跃时段" size="small">
              <n-space :size="6" align="center">
                <n-time-picker v-model:formatted-value="settings.active_start" format="HH:mm" value-format="HH:mm" size="small" style="width: 100px" />
                <span class="sep">→</span>
                <n-time-picker v-model:formatted-value="settings.active_end" format="HH:mm" value-format="HH:mm" size="small" style="width: 100px" />
              </n-space>
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-button size="small" type="primary" @click="saveSettings">保存设置</n-button>
        <span class="mono tip">心跳轮询已开启（60s）：页面常驻即可接收久坐提醒；小程序端由订阅消息承担。</span>
      </n-card>
    </n-space>
  </div>
</template>

<style scoped>
.log-row { display: flex; gap: 10px; font-size: 11px; color: #9fb8ce; padding: 4px 2px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.lt { color: #00e5a0; }
.lv { color: #38bdf8; }
.ln { flex: 1; color: #5b7290; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: #4a617f; font-size: 11px; padding: 8px 2px; }
.unit { color: #5b7290; font-size: 11px; }
.sep { color: #4a617f; }
.tip { display: block; margin-top: 10px; font-size: 10px; color: #46596f; }
:deep(.link-btn) { background: none; border: none; color: #00e5a0; cursor: pointer; }
</style>
