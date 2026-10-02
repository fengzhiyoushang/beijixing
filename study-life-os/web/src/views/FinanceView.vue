<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { financeApi } from '../api'
import StatCard from '../components/StatCard.vue'
import { categoryAxis, mountChart, valueAxis } from '../utils/chart'
import { thisMonth, todayStr } from '../utils/format'

const message = useMessage()

const month = ref(thisMonth())
const records = ref([])
const summary = ref(null)
const trendData = ref(null)
const budgetData = ref(null)

const modal = ref(false)
const editingId = ref(null)
const form = reactive({ type: 'expense', category: '餐饮', amount: null, is_study: false, note: '', occurred_at: todayStr() })
const budgetForm = reactive({ category: '*', limit_amount: null })

const CATS = ['餐饮', '交通', '娱乐', '购物', '日用品', '学习', '书籍', '课程', '生活费', '兼职', '其他']
const pieEl = ref(null)
const trendEl = ref(null)

async function loadAll() {
  records.value = await financeApi.records({ month: month.value })
  summary.value = await financeApi.summary(month.value)
  trendData.value = await financeApi.trend(6)
  budgetData.value = await financeApi.budgets(month.value)
  requestAnimationFrame(renderCharts)
}

function renderCharts() {
  if (!summary.value || !pieEl.value) return
  mountChart(pieEl.value, {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['50%', '52%'],
      itemStyle: { borderColor: '#0a111e', borderWidth: 2 }, label: { fontSize: 10, color: '#7d93b2' },
      data: summary.value.categories.map((c) => ({ name: c.category, value: c.amount })),
    }],
  })
  mountChart(trendEl.value, {
    legend: { textStyle: { color: '#7d93b2', fontSize: 10 }, top: 0 },
    xAxis: categoryAxis(trendData.value.map((t) => t.month.slice(2))),
    yAxis: valueAxis('¥'),
    series: [
      { name: '支出', type: 'bar', data: trendData.value.map((t) => t.expense), itemStyle: { color: '#ff5c7a', borderRadius: [3, 3, 0, 0] } },
      { name: '其中学习投入', type: 'bar', stack: 'e', data: trendData.value.map((t) => t.study_expense), itemStyle: { color: '#00e5a0' } },
      { name: '收入', type: 'line', smooth: true, data: trendData.value.map((t) => t.income), itemStyle: { color: '#38bdf8' } },
    ],
  })
}
onMounted(loadAll)

function openCreate() {
  editingId.value = null
  Object.assign(form, { type: 'expense', category: '餐饮', amount: null, is_study: false, note: '', occurred_at: todayStr() })
  modal.value = true
}
function openEdit(r) {
  editingId.value = r.id
  Object.assign(form, { ...r })
  modal.value = true
}
async function save() {
  if (!form.amount || form.amount <= 0) { message.warning('请输入金额'); return }
  const payload = { ...form, amount: Number(form.amount) }
  if (editingId.value) await financeApi.update(editingId.value, payload)
  else await financeApi.create(payload)
  modal.value = false
  loadAll()
}
async function remove(r) {
  await financeApi.remove(r.id)
  loadAll()
}
async function setBudget() {
  if (!budgetForm.limit_amount) return
  await financeApi.setBudget({ month: month.value, category: budgetForm.category, limit_amount: Number(budgetForm.limit_amount) })
  budgetForm.limit_amount = null
  loadAll()
}

const columns = [
  { title: '日期', key: 'occurred_at', width: 100 },
  { title: '分类', key: 'category', width: 90 },
  {
    title: '金额', key: 'amount', width: 110,
    render: (r) => h('span', { class: r.type === 'income' ? 'amt-in' : 'amt-out' },
      (r.type === 'income' ? '+' : '-') + ' ¥' + r.amount.toFixed(2)),
  },
  {
    title: '学习投入', key: 'is_study', width: 90,
    render: (r) => (r.is_study ? '✦ 学习' : '—'),
  },
  { title: '备注', key: 'note', ellipsis: { tooltip: true } },
  {
    title: '操作', key: 'ops', width: 110,
    render: (r) => h('div', {}, [
      h('button', { class: 'link-btn', onClick: () => openEdit(r) }, '改'),
      h('button', { class: 'link-btn danger', onClick: () => remove(r) }, '删'),
    ]),
  },
]
</script>

<template>
  <div class="page">
    <n-space vertical :size="14">
      <n-space align="center" justify="space-between">
        <n-space align="center" :size="10">
          <span class="mono label">月份</span>
          <n-date-picker v-model:formatted-value="month" type="month" value-format="yyyy-MM" size="small" style="width: 130px" @update:formatted-value="loadAll" />
        </n-space>
        <n-button type="primary" size="small" @click="openCreate">＋ 记一笔</n-button>
      </n-space>

      <n-grid v-if="summary" :cols="4" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:2 1000:1"><StatCard label="本月收入" :value="summary.income" color="#38bdf8" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="本月支出" :value="summary.expense" color="#ff5c7a" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="结余" :value="summary.balance" :sub="summary.balance >= 0 ? '保持盈余 ✓' : '注意超支 ⚠'" /></n-gi>
        <n-gi span="0:2 1000:1"><StatCard label="学习投入" :value="summary.study_expense" :sub="`占支出 ${Math.round(summary.study_ratio * 100)}%`" color="#fbbf24" /></n-gi>
      </n-grid>

      <n-grid :cols="6" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:6 1200:3">
          <n-card size="small" title="¥ 收支明细">
            <n-data-table :columns="columns" :data="records" size="small" :max-height="330" :pagination="{ pageSize: 12, simple: true }" />
          </n-card>
        </n-gi>
        <n-gi span="0:6 1200:3">
          <n-card size="small" title="◎ 学习投入专项分析">
            <div v-if="summary" class="study-bar">
              <n-progress type="line" :percentage="Math.round(summary.study_ratio * 100)" :color="'#fbbf24'" indicator-placement="inside" />
              <div class="mono note">学习类支出占总支出比例 · 共 {{ summary.study_items?.length || 0 }} 笔大额投入</div>
            </div>
            <div v-for="s in (summary?.study_items || [])" :key="s.id" class="study-row">
              <span class="sr-cat mono">{{ s.category }}</span>
              <span class="sr-note">{{ s.note || '学习投入' }}</span>
              <span class="sr-amt mono">¥{{ s.amount.toFixed(2) }}</span>
            </div>
            <div v-if="!summary?.study_items?.length" class="empty mono">// 本月暂无学习类支出记录</div>
          </n-card>
        </n-gi>
      </n-grid>

      <n-grid :cols="6" :x-gap="12" responsive="screen" item-responsive>
        <n-gi span="0:6 1200:2"><n-card size="small" title="本月支出结构"><div ref="pieEl" class="chart" /></n-card></n-gi>
        <n-gi span="0:6 1200:4"><n-card size="small" title="近 6 个月趋势（含学习投入堆叠）"><div ref="trendEl" class="chart" /></n-card></n-gi>
      </n-grid>

      <!-- 预算 -->
      <n-card size="small" title="▤ 预算管理">
        <n-space :size="8" align="center" style="margin-bottom: 10px">
          <n-select v-model:value="budgetForm.category" size="small" style="width: 120px"
            :options="[{ label: '总预算', value: '*' }, ...CATS.map((c) => ({ label: c, value: c }))]" />
          <n-input-number v-model:value="budgetForm.limit_amount" size="small" style="width: 130px" placeholder="金额" :min="0" />
          <n-button size="small" type="primary" @click="setBudget">设置预算</n-button>
        </n-space>
        <div v-for="b in (budgetData?.budgets || [])" :key="b.id" class="budget-row">
          <span class="bt-cat">{{ b.category === '*' ? '总预算' : b.category }}</span>
          <div class="bt-bar">
            <n-progress type="line" :percentage="Math.min(100, Math.round((b.usage_rate || 0) * 100))"
              :color="(b.usage_rate || 0) > 0.9 ? '#ff5c7a' : '#00e5a0'" :height="8" :show-indicator="false" />
          </div>
          <span class="mono bt-num">¥{{ b.used }} / {{ b.limit_amount }}（余 ¥{{ b.remaining }}）</span>
          <n-button size="tiny" quaternary type="error" @click="financeApi.deleteBudget(b.id).then(loadAll)">✕</n-button>
        </div>
        <div v-if="!budgetData?.budgets?.length" class="empty mono">// 未设置本月预算，给自己立个约束？</div>
      </n-card>
    </n-space>

    <!-- 记账弹窗 -->
    <n-modal v-model:show="modal" preset="card" :title="editingId ? '编辑记录' : '记一笔'" style="width: 420px">
      <n-form label-placement="top" size="small">
        <n-grid :cols="2" :x-gap="10">
          <n-gi>
            <n-form-item label="类型">
              <n-radio-group v-model:value="form.type" size="small">
                <n-radio-button value="expense">支出</n-radio-button>
                <n-radio-button value="income">收入</n-radio-button>
              </n-radio-group>
            </n-form-item>
          </n-gi>
          <n-gi><n-form-item label="金额"><n-input-number v-model:value="form.amount" :min="0" :precision="2" style="width: 100%" placeholder="¥" /></n-form-item></n-gi>
          <n-gi><n-form-item label="分类"><n-select v-model:value="form.category" :options="CATS.map((c) => ({ label: c, value: c }))" /></n-form-item></n-gi>
          <n-gi><n-form-item label="日期"><n-date-picker v-model:formatted-value="form.occurred_at" type="date" value-format="yyyy-MM-dd" style="width: 100%" /></n-form-item></n-gi>
        </n-grid>
        <n-form-item label="备注"><n-input v-model:value="form.note" placeholder="如：考研数学网课" /></n-form-item>
        <n-form-item label="标记为学习投入">
          <n-switch v-model:value="form.is_study" />
        </n-form-item>
        <n-space justify="end">
          <n-button @click="modal = false">取消</n-button>
          <n-button type="primary" @click="save">保存</n-button>
        </n-space>
      </n-form>
    </n-modal>
  </div>
</template>

<style scoped>
.label { color: #5b7290; font-size: 12px; }
.study-bar { margin-bottom: 8px; }
.note { font-size: 10px; color: #5b7290; margin-top: 4px; }
.study-row { display: flex; gap: 10px; align-items: center; padding: 6px 2px; border-bottom: 1px dashed rgba(56,189,248,0.1); font-size: 12px; }
.sr-cat { color: #fbbf24; font-size: 10px; border: 1px solid rgba(251,191,36,0.35); padding: 0 6px; border-radius: 8px; }
.sr-note { flex: 1; color: #c9d6e8; }
.sr-amt { color: #ff8ba0; }
.empty { color: #4a617f; font-size: 12px; padding: 10px 2px; }
.budget-row { display: flex; align-items: center; gap: 12px; padding: 7px 2px; border-bottom: 1px dashed rgba(56,189,248,0.1); }
.bt-cat { width: 70px; font-size: 12px; }
.bt-bar { flex: 1; }
.bt-num { font-size: 11px; color: #9fb8ce; }
:deep(.amt-in) { color: #38bdf8; }
:deep(.amt-out) { color: #ff8ba0; }
:deep(.link-btn) { background: none; border: none; color: #00e5a0; cursor: pointer; font-size: 12px; margin-right: 8px; }
:deep(.link-btn.danger) { color: #ff5c7a; }
</style>
