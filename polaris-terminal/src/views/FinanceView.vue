<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NCheckbox, NDatePicker, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NRadio, NRadioGroup, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar, glowLine } from '../utils/chart'

const message = useMessage()
const f = computed(() => store.finance)

/* ── 月份切换 ── */
function fmtMonth(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
const curMonth = ref(fmtMonth(new Date()))
const isThisMonth = computed(() => curMonth.value === fmtMonth(new Date()))

async function switchMonth(m) {
  curMonth.value = m
  try { await store.loadFinanceMonth(m) }
  catch (err) { message.error('加载失败：' + err.message) }
}
function shiftMonth(delta) {
  const [y, mo] = curMonth.value.split('-').map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  switchMonth(fmtMonth(d))
}

/* ── 图表 ── */
const pieOption = computed(() => {
  const palette = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf']
  return {
    tooltip: { trigger: 'item', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 }, formatter: '{b} ¥{c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: '#9ca3af', fontSize: 10 }, itemWidth: 8, itemHeight: 8 },
    series: [
      {
        type: 'pie', radius: ['46%', '70%'], center: ['50%', '42%'],
        itemStyle: { borderColor: '#1e1e1e', borderWidth: 2 },
        label: { show: false },
        data: f.value.categories.map((c, i) => ({
          name: c.name, value: c.value,
          itemStyle: { color: palette[i % palette.length], shadowColor: palette[i % palette.length] + '88', shadowBlur: 10 },
        })),
      },
    ],
  }
})

const trendOption = computed(() => {
  const t = f.value.trend
  return {
    grid: { left: 42, right: 16, top: 28, bottom: 26 },
    legend: { data: ['支出', '学习投入', '收入'], textStyle: { color: '#9ca3af', fontSize: 11 }, top: 0, right: 0 },
    xAxis: { type: 'category', data: t.months, ...axisBase(), splitLine: { show: false } },
    yAxis: { type: 'value', name: '¥', nameTextStyle: { color: '#6b7280', fontSize: 10 }, ...axisBase() },
    tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
    series: [
      { name: '支出', ...glowBar('#f87171'), data: t.expense, barWidth: '30%' },
      { name: '学习投入', ...glowBar('#4ade80'), data: t.study, barWidth: '30%' },
      { name: '收入', ...glowLine('#60a5fa'), data: t.income },
    ],
  }
})

const budgetRows = computed(() =>
  (f.value.budgets || []).map((b) => ({ ...b, rate: b.limit ? Math.round((b.used / b.limit) * 100) : 0, remain: b.limit - b.used })),
)

const studyRecords = computed(() => (f.value.records || []).filter((r) => r.study))

/* ── 记一笔 / 编辑流水 ── */
const CAT_EXPENSE = ['餐饮', '交通', '购物', '居住', '娱乐', '学习投入', '书籍', '课程', '文具', '考试报名', '医疗', '其他']
const CAT_INCOME = ['生活费', '兼职', '奖学金', '红包', '其他']
const PAYMENTS = ['微信', '支付宝', '现金', '银行卡']

const showRecord = ref(false)
const editingId = ref(null)
const saving = ref(false)
const recForm = ref({ type: 'expense', category: '餐饮', amount: null, date: Date.now(), note: '', is_study: false, payment_method: '微信' })

const catOptions = computed(() =>
  (recForm.value.type === 'expense' ? CAT_EXPENSE : CAT_INCOME).map((c) => ({ label: c, value: c })))

function openRecord(r) {
  editingId.value = r?.id ?? null
  if (r) {
    recForm.value = {
      type: r.type, category: r.categoryRaw, amount: r.amountRaw,
      date: new Date(r.dateFull + 'T12:00:00').getTime(), note: r.item === r.categoryRaw ? '' : r.item,
      is_study: !!r.study, payment_method: r.payment || '微信',
    }
  } else {
    recForm.value = { type: 'expense', category: '餐饮', amount: null, date: Date.now(), note: '', is_study: false, payment_method: '微信' }
  }
  showRecord.value = true
}
watch(() => recForm.value.type, (t) => {
  const list = t === 'expense' ? CAT_EXPENSE : CAT_INCOME
  if (!list.includes(recForm.value.category)) recForm.value.category = list[0]
  recForm.value.is_study = t === 'expense' && recForm.value.category === '学习投入'
})
watch(() => recForm.value.category, (c) => {
  if (c === '学习投入') recForm.value.is_study = true
})

async function saveRecord() {
  const v = recForm.value
  if (!v.amount || v.amount <= 0) { message.warning('请输入大于 0 的金额'); return }
  const d = new Date(v.date)
  const payload = {
    type: v.type, category: v.category, amount: Number(v.amount),
    occurred_at: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T12:00:00`,
    note: v.note || null, is_study: v.is_study, payment_method: v.payment_method,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await store.updateFinanceRecord(editingId.value, payload)
      message.success('记录已更新')
    } else {
      await store.addFinanceRecord(payload)
      message.success('已记一笔')
    }
    showRecord.value = false
    if (!isThisMonth.value) await store.loadFinanceMonth(curMonth.value)
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    saving.value = false
  }
}

async function removeRecord(r) {
  try {
    await store.removeFinanceRecord(r.id)
    message.success('已删除')
    if (!isThisMonth.value) await store.loadFinanceMonth(curMonth.value)
  } catch (err) { message.error('删除失败：' + err.message) }
}

/* ── 预算设置 ── */
const showBudget = ref(false)
const budgetSaving = ref(false)
const budgetForm = ref({ category: '*', limit_amount: null })
const budgetCatOptions = computed(() => [
  { label: '总预算（全部支出）', value: '*' },
  ...CAT_EXPENSE.map((c) => ({ label: c, value: c })),
])

function openBudget(b) {
  budgetForm.value = { category: b ? (b.name === '总预算' ? '*' : b.name) : '*', limit_amount: b?.limit ?? null }
  showBudget.value = true
}
async function saveBudget() {
  const v = budgetForm.value
  if (!v.limit_amount || v.limit_amount <= 0) { message.warning('请输入大于 0 的预算额度'); return }
  budgetSaving.value = true
  try {
    await store.setFinanceBudget({ month: curMonth.value, category: v.category, limit_amount: Number(v.limit_amount) })
    message.success('预算已保存')
    showBudget.value = false
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    budgetSaving.value = false
  }
}
async function removeBudget(b) {
  try {
    await store.removeFinanceBudget(b.id)
    message.success('预算已删除')
  } catch (err) { message.error('删除失败：' + err.message) }
}

onMounted(() => { if (!f.value.month) switchMonth(fmtMonth(new Date())) })
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>资产财务</h2>
      <span class="sub mono">FINANCE · {{ f.month || curMonth }} · 学习投入专项分析</span>
      <span class="spacer" />
      <div class="month-switch">
        <button class="ms-btn" @click="shiftMonth(-1)">◀</button>
        <span class="ms-cur mono">{{ curMonth }}</span>
        <button class="ms-btn" @click="shiftMonth(1)">▶</button>
        <button v-if="!isThisMonth" class="ms-btn ms-today" @click="switchMonth(fmtMonth(new Date()))">本月</button>
      </div>
      <NButton size="small" type="primary" @click="openRecord(null)">＋ 记一笔</NButton>
      <NButton size="small" tertiary @click="openBudget(null)">设置预算</NButton>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">¥{{ f.income }}</div>
        <div class="label-3">本月收入</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#f87171; text-shadow:0 0 14px #f8717166">¥{{ f.expense }}</div>
        <div class="label-3">本月支出</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big">¥{{ f.balance }}</div>
        <div class="label-3">本月结余</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">{{ f.studyRatio }}%</div>
        <div class="label-3">学习投入占支出（¥{{ f.studyExpense }}）</div>
      </div>
    </div>

    <div class="grid">
      <section class="col-4 card">
        <header class="card-head"><div class="card-title">◔ 支出结构 <span class="en">COMPOSITION</span></div></header>
        <div v-if="!f.categories.length" class="empty-tip">该月暂无支出记录</div>
        <GlowChart v-else :option="pieOption" height="248px" />
      </section>

      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">◱ 近 6 个月收支趋势 <span class="en">6-MONTH TREND</span></div>
          <span class="chip chip-blue">学习投入持续走高</span>
        </header>
        <GlowChart :option="trendOption" height="248px" />
      </section>

      <section class="col-5 card">
        <header class="card-head">
          <div class="card-title">▤ 预算执行 <span class="en">BUDGET</span></div>
          <NButton size="tiny" tertiary @click="openBudget(null)">＋ 设置</NButton>
        </header>
        <div v-if="!budgetRows.length" class="empty-tip">尚未设置预算，点击右上角「设置预算」</div>
        <div v-for="b in budgetRows" :key="b.name" class="budget-row">
          <div class="b-top">
            <span class="b-name">{{ b.name }}</span>
            <span class="mono b-num">
              ¥{{ b.used }} / {{ b.limit }}
              <button class="row-act" title="修改额度" @click="openBudget(b)">✎</button>
              <button class="row-act del" title="删除预算" @click="removeBudget(b)">×</button>
            </span>
          </div>
          <div class="b-track">
            <div class="b-fill" :style="{ width: Math.min(100, b.rate) + '%', background: b.rate > 90 ? '#f87171' : b.rate > 75 ? '#facc15' : '#4ade80' }" />
          </div>
          <div class="b-meta mono">
            <span :class="b.rate > 90 ? 'red' : 'c3'">已用 {{ b.rate }}%</span>
            <span class="c3">剩余 ¥{{ b.remain.toFixed(0) }}</span>
          </div>
        </div>
      </section>

      <section class="col-7 card">
        <header class="card-head">
          <div class="card-title">✦ 当月流水 <span class="en">RECORDS · {{ f.records.length }}</span></div>
          <NButton size="tiny" type="primary" @click="openRecord(null)">＋ 记一笔</NButton>
        </header>
        <div class="rec-head mono">
          <span style="width:74px">日期</span><span style="flex:1">项目</span><span style="width:88px">类别</span><span style="width:78px">方式</span><span style="width:88px">金额</span><span style="width:52px"></span>
        </div>
        <div v-if="!f.records.length" class="empty-tip">该月暂无流水，点「记一笔」开始记账</div>
        <div v-for="r in f.records" :key="r.id" class="rec-row">
          <span class="mono c3" style="width:74px">{{ r.date }}</span>
          <span style="flex:1">{{ r.item }}</span>
          <span style="width:88px">
            <span class="chip" :class="r.study ? 'chip-accent' : r.amount > 0 ? 'chip-blue' : ''">{{ r.cat }}</span>
          </span>
          <span class="mono c3" style="width:78px">{{ r.payment || '—' }}</span>
          <span class="mono" style="width:88px; text-align:right" :style="{ color: r.amount > 0 ? '#60a5fa' : '#f87171' }">
            {{ r.amount > 0 ? '+' : '' }}{{ r.amount }}
          </span>
          <span style="width:52px; text-align:right" class="row-btns">
            <button class="row-act" title="编辑" @click="openRecord(r)">✎</button>
            <NPopconfirm @positive-click="removeRecord(r)">
              <template #trigger><button class="row-act del" title="删除">×</button></template>
              删除这笔记录？
            </NPopconfirm>
          </span>
        </div>
      </section>
    </div>

    <!-- 记一笔 / 编辑 -->
    <NModal v-model:show="showRecord" preset="card" :title="editingId ? '编辑记录' : '记一笔'" style="width: 420px">
      <NForm label-placement="left" label-width="72">
        <NFormItem label="类型">
          <NRadioGroup v-model:value="recForm.type" size="small">
            <NRadio value="expense">支出</NRadio>
            <NRadio value="income">收入</NRadio>
          </NRadioGroup>
        </NFormItem>
        <NFormItem label="分类">
          <NSelect v-model:value="recForm.category" :options="catOptions" size="small" />
        </NFormItem>
        <NFormItem label="金额">
          <NInputNumber v-model:value="recForm.amount" :min="0.01" :max="1000000" :precision="2" placeholder="0.00" style="width:100%" size="small">
            <template #prefix>¥</template>
          </NInputNumber>
        </NFormItem>
        <NFormItem label="日期">
          <NDatePicker v-model:value="recForm.date" type="date" size="small" style="width:100%" />
        </NFormItem>
        <NFormItem label="支付方式">
          <NSelect v-model:value="recForm.payment_method" :options="PAYMENTS.map((p) => ({ label: p, value: p }))" size="small" />
        </NFormItem>
        <NFormItem v-if="recForm.type === 'expense'" label="学习投入">
          <NCheckbox v-model:checked="recForm.is_study">计入学习投入专项</NCheckbox>
        </NFormItem>
        <NFormItem label="备注">
          <NInput v-model:value="recForm.note" size="small" placeholder="如：图书馆考研资料" clearable />
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showRecord = false">取消</NButton>
          <NButton size="small" type="primary" :loading="saving" @click="saveRecord">保存</NButton>
        </div>
      </template>
    </NModal>

    <!-- 预算设置 -->
    <NModal v-model:show="showBudget" preset="card" title="设置预算" style="width: 380px">
      <NForm label-placement="left" label-width="72">
        <NFormItem label="月份"><span class="mono">{{ curMonth }}</span></NFormItem>
        <NFormItem label="类别">
          <NSelect v-model:value="budgetForm.category" :options="budgetCatOptions" size="small" />
        </NFormItem>
        <NFormItem label="额度">
          <NInputNumber v-model:value="budgetForm.limit_amount" :min="1" :max="10000000" :precision="0" placeholder="0" style="width:100%" size="small">
            <template #prefix>¥</template>
          </NInputNumber>
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showBudget = false">取消</NButton>
          <NButton size="small" type="primary" :loading="budgetSaving" @click="saveBudget">保存</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }

.month-switch { display: flex; align-items: center; gap: 6px; margin-right: 8px; }
.ms-btn { background: var(--card); border: 1px solid var(--border); color: var(--text-2, #9ca3af); border-radius: 6px; padding: 3px 9px; cursor: pointer; font-size: 12px; }
.ms-btn:hover { color: #4ade80; border-color: #4ade8066; }
.ms-cur { color: var(--text-1, #e5e7eb); font-size: 13px; min-width: 74px; text-align: center; }
.ms-today { color: #60a5fa; }

.empty-tip { color: #6b7280; font-size: 12px; text-align: center; padding: 28px 0; border: 1px dashed var(--border); border-radius: 8px; }

.budget-row { padding: 8px 0; border-bottom: 1px dashed var(--border); }
.budget-row:last-child { border-bottom: none; }
.b-top { display: flex; justify-content: space-between; margin-bottom: 6px; }
.b-name { font-size: 13px; }
.b-num { font-size: 12px; color: #9ca3af; }
.b-track { height: 6px; background: rgba(107,114,128,.18); border-radius: 3px; overflow: hidden; }
.b-fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
.b-meta { display: flex; justify-content: space-between; font-size: 11px; margin-top: 5px; }
.red { color: #f87171; }
.c3 { color: #6b7280; }

.rec-head { display: flex; gap: 8px; font-size: 11px; color: #6b7280; padding: 0 4px 8px; border-bottom: 1px solid var(--border); }
.rec-row { display: flex; gap: 8px; align-items: center; font-size: 12px; padding: 8px 4px; border-bottom: 1px dashed var(--border); }
.rec-row:last-child { border-bottom: none; }
.rec-row:hover .row-btns { opacity: 1; }
.row-btns { opacity: 0; transition: opacity .15s; }
.row-act { background: none; border: 1px solid var(--border); color: #9ca3af; border-radius: 5px; width: 22px; height: 22px; cursor: pointer; font-size: 12px; line-height: 1; }
.row-act:hover { color: #60a5fa; border-color: #60a5fa66; }
.row-act.del:hover { color: #f87171; border-color: #f8717166; }
</style>
