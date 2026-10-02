<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { classroomApi, predictApi } from '../api'

const buildings = ref([])
const records = ref([])
const sel = reactive({ building: null, room: null })
const pattern = ref(null)
const predCtl = reactive({
  weekday: new Date().getDay() === 0 ? 7 : new Date().getDay(),
  hour: new Date().getHours(),
})
const pred = ref(null)
const predLoading = ref(false)

const roomOpts = ref([])

async function loadBase() {
  buildings.value = await classroomApi.buildings()
  records.value = await classroomApi.records({ limit: 30 })
  if (buildings.value.length && !sel.building) {
    sel.building = buildings.value[0].building
    onBuildingChange()
  }
}
onMounted(loadBase)

function onBuildingChange() {
  const b = buildings.value.find((x) => x.building === sel.building)
  roomOpts.value = (b?.rooms || []).map((r) => ({ label: r, value: r }))
  sel.room = roomOpts.value[0]?.value || null
  if (sel.room) loadPattern()
}

async function loadPattern() {
  pattern.value = await classroomApi.pattern(sel.building, sel.room)
}

async function runPredict() {
  predLoading.value = true
  try {
    pred.value = await predictApi(predCtl.weekday, predCtl.hour)
  } finally { predLoading.value = false }
}

function cellStyle(rate) {
  if (rate == null) return { background: 'rgba(20,30,48,0.5)', color: '#33475f' }
  const hue = rate * 140
  return {
    background: `hsla(${hue}, 72%, ${16 + rate * 12}%, 0.85)`,
    border: `1px solid hsla(${hue}, 80%, 45%, 0.35)`,
    color: rate > 0.55 ? '#d9ffe9' : '#ffb9c6',
  }
}

const wdText = (w) => `周${'日一二三四五六'[w === 7 ? 0 : w]}`
const columns = [
  { title: '教学楼', key: 'building', width: 90 },
  { title: '教室', key: 'room', width: 90 },
  {
    title: '状态', key: 'occupied', width: 80,
    render: (r) => h('span', { class: 'pill ' + (r.occupied ? 'busy' : 'free') }, r.occupied ? '占用' : '空闲'),
  },
  { title: '备注', key: 'note', ellipsis: { tooltip: true } },
  {
    title: '采集时间', key: 'visited_at', width: 150,
    render: (r) => (r.visited_at || '').replace('T', ' ').slice(5, 16),
  },
  {
    title: '照片', key: 'photo_url', width: 70,
    render: (r) => r.photo_url
      ? h('img', { src: r.photo_url, class: 'thumb' })
      : '—',
  },
]
</script>

<template>
  <div class="page">
    <n-grid :cols="5" :x-gap="12" responsive="screen" item-responsive>
      <!-- 左：规律分析 -->
      <n-gi span="0:5 1200:3">
        <n-card size="small" title="⌗ 历史规律分析（weekday × hour 空闲率热力）">
          <n-space :size="8" align="center" style="margin-bottom: 10px">
            <n-select v-model:value="sel.building" size="small" style="width: 130px"
              :options="buildings.map((b) => ({ label: b.building, value: b.building }))"
              @update:value="onBuildingChange" />
            <n-select v-model:value="sel.room" size="small" style="width: 130px" :options="roomOpts"
              @update:value="loadPattern" />
            <n-tag v-if="pattern" size="small" :bordered="false" type="info">样本 {{ pattern.samples }}</n-tag>
          </n-space>
          <div v-if="!buildings.length" class="empty mono">// 尚无采集数据：请在小程序「空教室」页拍照标注，数据将实时同步到这里</div>
          <div v-else-if="pattern" class="heat">
            <div class="heat-row head">
              <div class="wd-cell mono">时间</div>
              <div v-for="h in pattern.hours" :key="h" class="hd-cell mono">{{ h }}</div>
            </div>
            <div v-for="row in pattern.matrix" :key="row[0].weekday" class="heat-row">
              <div class="wd-cell mono">{{ wdText(row[0].weekday) }}</div>
              <div v-for="c in row" :key="c.hour" class="hd-cell cell" :style="cellStyle(c.rate)"
                :title="`${c.total ? `空闲 ${c.free}/${c.total}` : '无样本'}`">
                {{ c.rate == null ? '' : Math.round(c.rate * 100) }}
              </div>
            </div>
          </div>
        </n-card>
      </n-gi>

      <!-- 右：空闲预测 -->
      <n-gi span="0:5 1200:2">
        <n-card size="small" title="◎ 空闲预测引擎">
          <n-space :size="8" align="center" style="margin-bottom: 10px">
            <n-select v-model:value="predCtl.weekday" size="small" style="width: 96px"
              :options="[1, 2, 3, 4, 5, 6, 7].map((v) => ({ label: wdText(v), value: v }))" />
            <n-select v-model:value="predCtl.hour" size="small" style="width: 96px"
              :options="Array.from({ length: 15 }, (_, i) => ({ label: `${i + 8}:00`, value: i + 8 }))" />
            <n-button size="small" type="primary" :loading="predLoading" @click="runPredict">预测</n-button>
          </n-space>
          <div v-if="pred && !pred.results.length" class="empty mono">// {{ pred.hint }}</div>
          <div v-for="r in (pred?.results || [])" :key="r.room + r.building" class="pred-row">
            <div class="pr-left">
              <div class="pr-name">{{ r.building }} · {{ r.room }}</div>
              <div class="pr-meta mono">样本 {{ r.samples }} · {{ r.last_occupied == null ? '' : (r.last_visited || '').slice(5, 10) }}</div>
            </div>
            <div class="pr-score">
              <div class="num mono" :class="{ good: r.confidence >= 70, mid: r.confidence >= 40 && r.confidence < 70 }">{{ r.confidence }}</div>
              <div class="bar"><div class="fill" :style="{ width: r.confidence + '%' }" /></div>
            </div>
          </div>
          <div class="pred-note mono">算法：个人采集空闲率（时间衰减加权）− 课程占用惩罚</div>
        </n-card>
      </n-gi>
    </n-grid>

    <n-card size="small" title="☰ 最近采集快照" style="margin-top: 12px">
      <n-data-table :columns="columns" :data="records" size="small" :bordered="false" :max-height="300" />
    </n-card>
  </div>
</template>

<style scoped>
.empty { color: #4a617f; font-size: 12px; padding: 16px 4px; }
.heat { overflow-x: auto; }
.heat-row { display: flex; margin-bottom: 3px; }
.heat-row.head .hd-cell, .heat-row.head .wd-cell { color: #5b7290; font-size: 10px; }
.wd-cell { width: 42px; flex: none; font-size: 11px; color: #7d93b2; display: flex; align-items: center; }
.hd-cell { flex: 1; min-width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; font-size: 10px; border-radius: 4px; margin-right: 3px; }
.cell { cursor: help; transition: transform 0.1s; }
.cell:hover { transform: scale(1.12); z-index: 2; }
.pred-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 4px; border-bottom: 1px dashed rgba(56,189,248,0.12); }
.pr-name { font-size: 13px; color: #dce8f7; }
.pr-meta { font-size: 10px; color: #5b7290; margin-top: 2px; }
.pr-score { text-align: right; width: 90px; }
.pr-score .num { font-size: 18px; color: #7d93b2; }
.pr-score .num.good { color: #00e5a0; text-shadow: 0 0 10px rgba(0,229,160,0.5); }
.pr-score .num.mid { color: #fbbf24; }
.bar { height: 3px; background: rgba(56,189,248,0.12); border-radius: 2px; margin-top: 3px; }
.fill { height: 100%; background: linear-gradient(90deg, #0aa8d8, #00e5a0); border-radius: 2px; }
.pred-note { margin-top: 10px; font-size: 10px; color: #46596f; }
:deep(.pill) { font-size: 11px; padding: 1px 8px; border-radius: 10px; }
:deep(.pill.free) { color: #00e5a0; background: rgba(0,229,160,0.1); border: 1px solid rgba(0,229,160,0.3); }
:deep(.pill.busy) { color: #ff5c7a; background: rgba(255,92,122,0.1); border: 1px solid rgba(255,92,122,0.3); }
:deep(.thumb) { width: 44px; height: 32px; object-fit: cover; border-radius: 4px; border: 1px solid rgba(56,189,248,0.25); }
</style>
