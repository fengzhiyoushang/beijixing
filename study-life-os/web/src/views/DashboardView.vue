<script setup>
import { onMounted, ref } from 'vue'
import { dashboardApi } from '../api'
import StatCard from '../components/StatCard.vue'
import { categoryAxis, mountChart, valueAxis } from '../utils/chart'
import { fmtRemaining, weekdayCn } from '../utils/format'

const data = ref(null)
const trendEl = ref(null)
const barEl = ref(null)
const pieEl = ref(null)

const statusMeta = {
  upcoming: { type: 'info', text: '待上' },
  ongoing: { type: 'success', text: '进行中' },
  past: { type: 'default', text: '已结束' },
}

function renderCharts(d) {
  const t14 = d.charts.task_trend14
  mountChart(trendEl.value, {
    xAxis: categoryAxis(t14.map((x) => x.date.slice(5))),
    yAxis: valueAxis(),
    series: [{ name: '完成任务', type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: t14.map((x) => x.done) }],
  })
  const c14 = d.charts.checkin_trend14
  mountChart(barEl.value, {
    xAxis: categoryAxis(c14.map((x) => x.date.slice(5))),
    yAxis: valueAxis('min'),
    series: [{ name: '专注分钟', type: 'bar', barWidth: '55%', data: c14.map((x) => x.minutes), itemStyle: { borderRadius: [3, 3, 0, 0] } }],
  })
  mountChart(pieEl.value, {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['50%', '54%'],
      itemStyle: { borderColor: '#0a111e', borderWidth: 2 },
      label: { color: '#7d93b2', fontSize: 10 },
      data: d.charts.expense_categories.map((c) => ({ name: c.category, value: c.amount })),
    }],
  })
}

async function load() {
  data.value = await dashboardApi.summary()
  requestAnimationFrame(() => renderCharts(data.value))
}
onMounted(load)
</script>

<template>
  <div class="page" v-if="data">
    <n-space vertical :size="14">
      <!-- 提醒条 -->
      <n-alert v-for="(a, i) in data.alerts" :key="i" :type="a.level === 'danger' ? 'error' : a.level === 'warning' ? 'warning' : 'info'" :bordered="false" size="small">
        {{ a.text }}
      </n-alert>

      <!-- 统计卡 -->
      <n-grid :cols="8" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="今日课程" :value="data.classes_today.length" :sub="`周${'日一二三四五六'[data.weekday === 7 ? 0 : data.weekday]} · ${data.date}`" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="待办 DDL" :value="data.tasks.pending" :sub="`今日到期 ${data.tasks.due_today}`" color="#38bdf8" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="逾期任务" :value="data.tasks.overdue" :sub="`完成率 ${Math.round(data.tasks.completion_rate * 100)}%`" color="#ff5c7a" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="今日专注" :value="`${data.checkin.today_minutes}m`" :sub="`连续 ${data.checkin.streak_days} 天`" color="#a78bfa" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="本月结余" :value="data.finance.balance" :sub="`支出 ${data.finance.expense}`" :color="data.finance.balance >= 0 ? '#00e5a0' : '#ff5c7a'" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="学习投入" :value="data.finance.study_expense" :sub="`占比 ${Math.round(data.finance.study_ratio * 100)}%`" color="#fbbf24" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="考研倒计时" :value="data.kaoyan ? `${data.kaoyan.days_left}天` : '—'" :sub="data.kaoyan ? `${data.kaoyan.target_school} · 差${data.kaoyan.gap}分` : '未设目标'" color="#f472b6" /></n-gi>
        <n-gi span="0:4 640:2 1280:1"><StatCard label="昨日睡眠" :value="data.health.sleep_yesterday_minutes ? `${Math.floor(data.health.sleep_yesterday_minutes / 60)}h${data.health.sleep_yesterday_minutes % 60}m` : '—'" :sub="data.health.sedentary.should_break ? '该起身活动了!' : '久坐状态正常'" :color="data.health.sedentary.should_break ? '#ff5c7a' : '#34d399'" /></n-gi>
      </n-grid>

      <!-- 列表区 -->
      <n-grid :cols="3" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:3 1100:1">
          <n-card title="今日课表" size="small">
            <div v-if="!data.classes_today.length" class="empty mono">// 今天没有课，自由日 🎯</div>
            <div v-for="c in data.classes_today" :key="c.course + c.start_time" class="class-row">
              <span class="mono time">{{ c.start_time }}</span>
              <div class="info">
                <div class="name">{{ c.course }} <span class="loc">◈ {{ c.location || '待定' }}</span></div>
              </div>
              <n-tag size="tiny" :type="statusMeta[c.class_status].type" :bordered="false">{{ statusMeta[c.class_status].text }}</n-tag>
            </div>
          </n-card>
        </n-gi>
        <n-gi span="0:3 1100:2">
          <n-card title="DDL 倒计时" size="small">
            <div v-if="!data.upcoming_tasks.length" class="empty mono">// 未来没有临近的截止日期，保持节奏 ✅</div>
            <div v-for="t in data.upcoming_tasks" :key="t.id" class="task-row">
              <n-tag size="tiny" :bordered="false" :type="t.priority === 'high' ? 'error' : t.priority === 'medium' ? 'warning' : 'default'">{{ t.priority === 'high' ? '高' : t.priority === 'medium' ? '中' : '低' }}</n-tag>
              <span class="t-title">{{ t.title }}</span>
              <span class="t-due mono">{{ weekdayCn(t.due_at) }} {{ t.due_at.slice(11, 16) }}</span>
              <n-tag size="tiny" class="mono" :bordered="false" type="info">{{ fmtRemaining(t.remaining_seconds) }}</n-tag>
            </div>
          </n-card>
        </n-gi>
      </n-grid>

      <!-- 图表区 -->
      <n-grid :cols="3" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:3 1100:1"><n-card title="近 14 天任务完成" size="small"><div ref="trendEl" class="chart" /></n-card></n-gi>
        <n-gi span="0:3 1100:1"><n-card title="近 14 天学习专注(分钟)" size="small"><div ref="barEl" class="chart" /></n-card></n-gi>
        <n-gi span="0:3 1100:1"><n-card title="本月支出结构" size="small"><div ref="pieEl" class="chart" /></n-card></n-gi>
      </n-grid>
    </n-space>
  </div>
  <div v-else class="page loading mono">// loading terminal data …</div>
</template>

<style scoped>
.empty { color: #4a617f; font-size: 12px; padding: 10px 2px; }
.class-row { display: flex; align-items: center; gap: 10px; padding: 7px 4px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.class-row:last-child { border-bottom: none; }
.class-row .time { color: #00e5a0; font-size: 13px; min-width: 42px; }
.class-row .name { font-size: 13px; color: #dce8f7; }
.class-row .loc { color: #7d93b2; font-size: 11px; }
.task-row { display: flex; align-items: center; gap: 10px; padding: 7px 4px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.task-row:last-child { border-bottom: none; }
.t-title { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-due { color: #7d93b2; font-size: 11px; }
.loading { color: #5b7290; padding-top: 60px; text-align: center; }
</style>
