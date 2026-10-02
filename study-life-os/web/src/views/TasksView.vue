<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { taskApi } from '../api'
import StatCard from '../components/StatCard.vue'
import { categoryAxis, mountChart, valueAxis } from '../utils/chart'
import { fmtDateTime, fmtRemaining, toLocalIso } from '../utils/format'

const message = useMessage()

const tasks = ref([])
const stats = ref(null)
const filters = reactive({ status: 'pending', category: null, search: '', within_days: null })
const drawer = ref(false)
const editingId = ref(null)
const quick = ref('')

const form = reactive({ title: '', description: '', category: 'study', priority: 'medium', due_at: null, progress: 0 })

const catOpts = [{ label: '学习', value: 'study' }, { label: '工作', value: 'work' }, { label: '生活', value: 'life' }]
const priOpts = [{ label: '高', value: 'high' }, { label: '中', value: 'medium' }, { label: '低', value: 'low' }]
const priType = { high: 'error', medium: 'warning', low: 'default' }
const priText = { high: '高优先级', medium: '中优先级', low: '低优先级' }

async function load() {
  const params = {}
  for (const k of ['status', 'category', 'search']) if (filters[k]) params[k] = filters[k]
  if (filters.within_days) params.within_days = filters.within_days
  tasks.value = await taskApi.list(params)
  stats.value = await taskApi.stats()
  renderCharts()
}

function renderCharts() {
  if (!stats.value) return
  mountChart(trendEl.value, {
    xAxis: categoryAxis(stats.value.trend14.map((x) => x.date.slice(5))),
    yAxis: valueAxis(),
    series: [{ type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: stats.value.trend14.map((x) => x.done), name: '完成数' }],
  })
  const cats = Object.entries(stats.value.by_category)
  mountChart(pieEl.value, {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['40%', '66%'], center: ['50%', '52%'],
      itemStyle: { borderColor: '#0a111e', borderWidth: 2 }, label: { fontSize: 10, color: '#7d93b2' },
      data: cats.map(([k, v]) => ({ name: { study: '学习', work: '工作', life: '生活' }[k] || k, value: v.pending + v.done })),
    }],
  })
}

onMounted(load)

function openCreate() {
  editingId.value = null
  Object.assign(form, { title: '', description: '', category: 'study', priority: 'medium', due_at: null, progress: 0 })
  drawer.value = true
}
function openEdit(t) {
  editingId.value = t.id
  Object.assign(form, { ...t, due_at: t.due_at ? new Date(t.due_at).getTime() : null })
  drawer.value = true
}

async function save() {
  const payload = { ...form, description: form.description || null }
  if (typeof payload.due_at === 'number') payload.due_at = toLocalIso(payload.due_at)
  if (editingId.value) await taskApi.update(editingId.value, payload)
  else await taskApi.create(payload)
  drawer.value = false
  message.success('已保存')
  load()
}

async function quickAdd() {
  if (!quick.value.trim()) return
  await taskApi.create({ title: quick.value.trim(), category: 'study', priority: 'medium' })
  quick.value = ''
  message.success('已添加')
  load()
}

async function complete(t) {
  await taskApi.complete(t.id)
  load()
}
async function remove(t) {
  await taskApi.remove(t.id)
  load()
}

const trendEl = ref(null)
const pieEl = ref(null)
</script>

<template>
  <div class="page">
    <n-space vertical :size="14">
      <!-- 快速录入 -->
      <n-input-group>
        <n-input v-model:value="quick" placeholder="⚡ 快速记录一个 DDL，回车即存（详细管理用右侧新建）" @keyup.enter="quickAdd" />
        <n-button type="primary" @click="quickAdd">录入</n-button>
      </n-input-group>

      <!-- 统计 -->
      <n-grid v-if="stats" :cols="5" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:2 900:1"><StatCard label="总任务" :value="stats.total" color="#38bdf8" /></n-gi>
        <n-gi span="0:2 900:1"><StatCard label="进行中" :value="stats.pending" sub="待处理" /></n-gi>
        <n-gi span="0:2 900:1"><StatCard label="逾期" :value="stats.overdue" color="#ff5c7a" /></n-gi>
        <n-gi span="0:2 900:1"><StatCard label="完成率" :value="`${Math.round(stats.completion_rate * 100)}%`" :sub="`已完成 ${stats.done}`" /></n-gi>
        <n-gi span="0:2 900:1"><StatCard label="今日到期" :value="stats.due_today" color="#fbbf24" /></n-gi>
      </n-grid>

      <!-- 列表 -->
      <n-card size="small" title="任务清单">
        <template #header-extra>
          <n-space :size="8">
            <n-select v-model:value="filters.status" :options="[{ label: '进行中', value: 'pending' }, { label: '已完成', value: 'done' }, { label: '全部', value: null }]" size="tiny" style="width: 92px" @update:value="load" />
            <n-select v-model:value="filters.category" clearable :options="catOpts" size="tiny" style="width: 84px" placeholder="分类" @update:value="load" />
            <n-input v-model:value="filters.search" size="tiny" placeholder="搜索" clearable style="width: 110px" @keyup.enter="load" />
            <n-button size="tiny" type="primary" @click="openCreate">＋ 新建</n-button>
          </n-space>
        </template>

        <div v-if="!tasks.length" class="empty mono">// 无任务。给未来的自己立个 flag？</div>
        <div v-for="t in tasks" :key="t.id" class="task" :class="{ done: t.status === 'done', overdue: t.overdue }">
          <n-checkbox :checked="t.status === 'done'" @update:checked="t.status === 'done' ? null : complete(t)" />
          <div class="body">
            <div class="row1">
              <span class="title" :class="{ strike: t.status === 'done' }">{{ t.title }}</span>
              <n-tag size="tiny" :bordered="false" :type="priType[t.priority]">{{ priText[t.priority] }}</n-tag>
              <n-tag size="tiny" :bordered="false">{{ { study: '学习', work: '工作', life: '生活' }[t.category] }}</n-tag>
            </div>
            <div class="row2 mono">
              <span v-if="t.due_at">⏳ {{ fmtDateTime(t.due_at) }}</span>
              <n-tag v-if="t.status === 'pending' && t.due_at" size="tiny" :bordered="false" :type="t.overdue ? 'error' : 'info'" class="cd">
                {{ t.overdue ? '⚠ 已逾期' : `剩余 ${fmtRemaining(t.remaining_seconds)}` }}
              </n-tag>
            </div>
            <n-progress v-if="t.progress > 0 && t.status !== 'done'" type="line" :percentage="t.progress" :height="4" :show-indicator="false" processing />
          </div>
          <div class="ops">
            <n-button size="tiny" quaternary @click="openEdit(t)">编辑</n-button>
            <n-popconfirm @positive-click="remove(t)">
              <template #trigger><n-button size="tiny" quaternary type="error">删除</n-button></template>
              确定删除？
            </n-popconfirm>
          </div>
        </div>
      </n-card>

      <!-- 分析 -->
      <n-grid :cols="2" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:2 900:1"><n-card size="small" title="近 14 天完成趋势"><div ref="trendEl" class="chart" /></n-card></n-gi>
        <n-gi span="0:2 900:1"><n-card size="small" title="任务分类分布"><div ref="pieEl" class="chart" /></n-card></n-gi>
      </n-grid>
    </n-space>

    <!-- 编辑抽屉 -->
    <n-drawer v-model:show="drawer" :width="420" placement="right">
      <n-drawer-content :title="editingId ? '编辑任务' : '新建任务'" closable>
        <n-form label-placement="top" size="small">
          <n-form-item label="标题"><n-input v-model:value="form.title" /></n-form-item>
          <n-form-item label="描述"><n-input v-model:value="form.description" type="textarea" :rows="3" /></n-form-item>
          <n-grid :cols="2" :x-gap="10">
            <n-gi><n-form-item label="分类"><n-select v-model:value="form.category" :options="catOpts" /></n-form-item></n-gi>
            <n-gi><n-form-item label="优先级"><n-select v-model:value="form.priority" :options="priOpts" /></n-form-item></n-gi>
          </n-grid>
          <n-form-item label="截止时间"><n-date-picker v-model:value="form.due_at" type="datetime" style="width: 100%" /></n-form-item>
          <n-form-item label="进度"><n-slider v-model:value="form.progress" :step="5" /></n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button @click="drawer = false">取消</n-button>
            <n-button type="primary" @click="save">保存</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.task { display: flex; gap: 10px; align-items: flex-start; padding: 10px 6px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.task:last-child { border-bottom: none; }
.task.overdue .title { color: #ff8ba0; }
.body { flex: 1; min-width: 0; }
.row1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.title { font-size: 14px; color: #dce8f7; }
.strike { text-decoration: line-through; color: #4a617f; }
.row2 { display: flex; gap: 8px; align-items: center; margin-top: 4px; font-size: 11px; color: #7d93b2; }
.cd { font-family: Consolas, monospace; }
.ops { display: flex; }
.empty { color: #4a617f; font-size: 12px; padding: 12px 2px; }
</style>
