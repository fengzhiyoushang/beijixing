<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDatePicker, NDropdown, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import { fmtDate, fmtTime, greetingByHour } from '../utils/format'
import StatusDot from './StatusDot.vue'
import LlmConfigModal from './LlmConfigModal.vue'

const router = useRouter()
const message = useMessage()

/* ── 时钟 ── */
const now = ref(new Date())
let timer = null
onMounted(() => { timer = setInterval(() => (now.value = new Date()), 1000) })
onUnmounted(() => clearInterval(timer))

const greeting = computed(() => greetingByHour(now.value.getHours()))
/** 顶部大标题只取时间段，其余作为副句，避免一行过长被截断 */
const shortGreeting = computed(() => greeting.value.split('，')[0])
const dateText = computed(() => fmtDate(now.value))
const timeText = computed(() => fmtTime(now.value))

/* ── 新建 ── */
const showCreate = ref(false)
const creating = ref(false)
const form = ref({ title: '', priority: 'high', category: '考研' })
const priorityOptions = [
  { label: '高优先级', value: 'high' },
  { label: '中优先级', value: 'medium' },
  { label: '低优先级', value: 'low' },
]
const categoryOptions = ['考研', '课程', '知识整理', '生活'].map((c) => ({ label: c, value: c }))

const createOptions = [
  { label: '＋ 新建待办事项（可设截止时间）', key: 'note' },
  { type: 'divider', key: 'd0' },
  { label: '✎ 记录一笔支出', key: 'expense' },
  { label: '✦ 记录学习打卡', key: 'checkin' },
  { label: '⬆ 上传知识文档', key: 'doc' },
]

/* ── 截止时间：快捷预设 + 自定义（自主时间设置）── */
function endOfDay(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  d.setHours(23, 59, 0, 0)
  return d.getTime()
}
function nextSunday() {
  const d = new Date()
  const diff = (7 - d.getDay()) % 7 || 7        // 下一个周日
  d.setDate(d.getDate() + diff)
  d.setHours(23, 59, 0, 0)
  return d.getTime()
}
const duePresets = [
  { label: '今晚 23:59', value: () => endOfDay(0) },
  { label: '明晚 23:59', value: () => endOfDay(1) },
  { label: '三天后', value: () => endOfDay(3) },
  { label: '本周末', value: () => nextSunday() },
  { label: '一周后', value: () => endOfDay(7) },
]
const dueTs = ref(endOfDay(0))
const duePreset = ref('今晚 23:59')

function applyPreset(preset) {
  dueTs.value = preset.value()
  duePreset.value = preset.label
}
function clearDue() {
  dueTs.value = null
  duePreset.value = '无截止时间'
}

/** 时间戳 → 本地 naive ISO（后端按本地时间存储） */
function toLocalIso(ts) {
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`
}

function openCreate() {
  applyPreset(duePresets[0])            // 默认今晚 23:59，可在弹窗内自主调整
  showCreate.value = true
}

function handleCreate(key) {
  if (key === 'note') {
    openCreate()
    return
  }
  const label = createOptions.find((o) => o.key === key)?.label.replace(/^[＋✎✦⬆]\s*/, '')
  // 记账 / 打卡 / 上传文档：引导到对应模块用真实表单完成（避免造无效数据）
  const routeMap = { expense: '/finance', checkin: '/health', doc: '/knowledge' }
  if (routeMap[key]) {
    router.push(routeMap[key])
    message.info(`请在「${label.replace('记录', '').replace('上传', '')}」页完成真实录入`)
    return
  }
  message.info(`${label} · 请使用事项备忘页的表单`)
}

async function submitCreate() {
  if (!form.value.title.trim()) { message.warning('请填写事项标题'); return }
  creating.value = true
  try {
    await store.addNote({
      title: form.value.title.trim(),
      priority: form.value.priority,
      category: form.value.category,
      due: dueTs.value ? toLocalIso(dueTs.value) : null,
    })
    message.success(
      dueTs.value
        ? `已写入后端（截止 ${duePreset.value}），并同步到总览与小程序`
        : '已写入后端（无截止时间），可在「事项备忘」随时补充',
    )
    showCreate.value = false
    form.value.title = ''
  } catch (err) {
    message.error(err.message)
  } finally {
    creating.value = false
  }
}

/* 用户功能（个人资料/设置/退出）已迁移至左上角头像窗口，见 SideNav.vue */

/* ── Token 真实用量（后端 ai_usage 台账，非估算展示）── */
const showLlmConfig = ref(false)
const tokenRefreshing = ref(false)
function fmtTok(n) {
  const v = Number(n) || 0
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  return String(v)
}
const tokenText = computed(() => {
  const u = store.tokenSummary
  if (!u) return 'Token —'
  const used = fmtTok(u.total_tokens)
  if (u.remaining === null || u.remaining === undefined) return `Token ${used} · 未设预算`
  return `Token ${used} / 余 ${fmtTok(u.remaining)}`
})
const tokenTitle = computed(() => {
  const u = store.tokenSummary
  if (!u) return '点击刷新 Token 用量'
  return [
    `累计 ${u.total_tokens?.toLocaleString?.() ?? 0} tokens（${u.calls ?? 0} 次调用）`,
    `今日 ${u.today_tokens?.toLocaleString?.() ?? 0} · 近7天 ${u.week_tokens?.toLocaleString?.() ?? 0} · 近30天 ${u.month_tokens?.toLocaleString?.() ?? 0}`,
    u.remaining === null || u.remaining === undefined
      ? '剩余：未设置预算（可在模型配置中设置）'
      : `剩余 ${u.remaining?.toLocaleString?.() ?? 0} / 预算 ${u.quota?.toLocaleString?.() ?? 0}`,
    '点击刷新 · 数据来自 provider 回传的真实 usage',
  ].join('\n')
})
async function refreshToken() {
  if (tokenRefreshing.value) return
  tokenRefreshing.value = true
  try {
    await store.loadTokenUsage()
    message.success('Token 用量已刷新')
  } catch (err) {
    message.error(`刷新失败：${err.message}`)
  } finally {
    tokenRefreshing.value = false
  }
}
</script>

<template>
  <header class="topbar">
    <!-- 左：日期 + 大号问候语（参考稿排版） -->
    <div class="left">
      <div class="date-line mono">{{ dateText }} {{ timeText }}</div>
      <h1 class="greet">
        {{ shortGreeting }}，{{ store.profile.name }}。<span class="greet-sub">把今天做好，长期方向自然会变得清晰。</span>
      </h1>
    </div>

    <!-- 右：状态 / 天气 / 新建 / 头像 -->
    <div class="right">
      <div class="status-group">
        <span v-for="s in store.systemStatus" :key="s.label" class="status-item">
          <StatusDot :tone="s.tone" :label="s.label" />
        </span>
      </div>

      <div class="weather" :title="`${store.weather.city} ${store.weather.text} 空气质量${store.weather.aqi}`">
        <span class="w-icon">{{ store.weather.icon }}</span>
        <span class="w-city">{{ store.weather.city }}</span>
        <span class="w-temp mono">{{ store.weather.temp }}℃</span>
      </div>

      <!-- Token 真实消耗 / 剩余（点击刷新，齿轮打开模型配置） -->
      <div class="token-chip" :title="tokenTitle" @click="refreshToken">
        <span class="t-icon">◈</span>
        <span class="t-text mono">{{ tokenText }}</span>
        <button class="t-gear" title="大模型 API 配置" @click.stop="showLlmConfig = true">⚙</button>
      </div>

      <!-- 单个「＋ 新建」按钮：点开即包含「新建待办（可设截止时间）」与其它快捷入口 -->
      <NDropdown :options="createOptions" trigger="click" placement="bottom-end" @select="handleCreate">
        <NButton size="small" type="primary" class="new-btn">＋ 新建</NButton>
      </NDropdown>
    </div>

    <!-- 新建事项弹窗 -->
    <NModal
      v-model:show="showCreate"
      preset="card"
      title="新建待办事项"
      style="width: 460px"
      :bordered="false"
    >
      <div class="form">
        <div class="field">
          <label class="label-3">事项标题</label>
          <NInput v-model:value="form.title" placeholder="例如：完成操作系统实验报告" @keyup.enter="submitCreate" />
        </div>
        <div class="two">
          <div class="field">
            <label class="label-3">优先级</label>
            <NSelect v-model:value="form.priority" :options="priorityOptions" />
          </div>
          <div class="field">
            <label class="label-3">分类</label>
            <NSelect v-model:value="form.category" :options="categoryOptions" />
          </div>
        </div>
        <div class="field">
          <label class="label-3">截止时间（可自主设置）</label>
          <div class="due-quick">
            <button
              v-for="q in duePresets" :key="q.label"
              class="q-chip" :class="{ on: duePreset === q.label }"
              @click="applyPreset(q)"
            >{{ q.label }}</button>
            <button class="q-chip" :class="{ on: duePreset === '无截止时间' }" @click="clearDue">无截止时间</button>
          </div>
          <NDatePicker
            v-model:value="dueTs" type="datetime" clearable
            format="yyyy-MM-dd HH:mm" style="width: 100%"
            placeholder="或自定义日期与时间"
            @update:value="duePreset = '自定义时间'"
          />
          <div class="hint mono">
            {{ dueTs
              ? `将在 ${new Date(dueTs).toLocaleString('zh-CN', { hour12: false })} 到期 · 到点前 3 小时会推送提醒（需小程序授权订阅消息）`
              : '未设置截止时间：任务不会出现在「今日待推进」倒计时中' }}
          </div>
        </div>
      </div>
      <template #footer>
        <div class="footer">
          <NButton quaternary @click="showCreate = false">取消</NButton>
          <NButton type="primary" :loading="creating" @click="submitCreate">创建并同步</NButton>
        </div>
      </template>
    </NModal>

    <!-- 大模型 API 配置窗口 -->
    <LlmConfigModal v-model:show="showLlmConfig" />
  </header>
</template>

<style scoped>
.topbar {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex; align-items: center; gap: 18px;
  /* 右侧留出系统窗口按钮（最小化/最大化/关闭）覆盖区 */
  padding: 0 calc(26px + var(--wctl-w, 0px)) 0 26px;
  background: linear-gradient(180deg, rgba(11, 15, 13, 0.6), rgba(11, 15, 13, 0.25));
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(10px);
  position: relative; z-index: 3;
  /* 桌面版：顶栏作为无边框窗口的拖拽区 */
  -webkit-app-region: drag;
}
/* 桌面版：所有可交互元素退出拖拽区，否则无法点击 */
.topbar button,
.topbar .right,
.topbar .avatar-wrap,
.topbar :deep(.n-button),
.topbar :deep(.n-dropdown-trigger) { -webkit-app-region: no-drag; }

/* 左侧：日期 + 大号问候语 */
.left { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.date-line { font-size: 11.5px; color: var(--text-3); letter-spacing: 0.5px; }
.greet {
  margin: 0; font-size: 23px; font-weight: 700; letter-spacing: 0.5px; line-height: 1.3;
  color: var(--accent); text-shadow: 0 0 26px rgba(74, 222, 128, 0.28);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.greet-sub { color: var(--text-2); font-weight: 500; font-size: 19px; text-shadow: none; }

/* 右侧 */
.right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.status-group { display: flex; align-items: center; gap: 8px; }
.status-item {
  padding: 4px 10px; border: 1px solid var(--border); border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
}
.weather {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 11px; border: 1px solid var(--border); border-radius: 999px;
  background: rgba(255, 255, 255, 0.025); font-size: 12px; color: var(--text-2);
}
.w-icon { font-size: 13px; }
.w-temp { color: var(--text-1); font-weight: 600; }

/* Token 用量胶囊：真实台账数据，点击刷新 */
.token-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 6px 4px 11px; border: 1px solid rgba(96, 165, 250, 0.32); border-radius: 999px;
  background: rgba(96, 165, 250, 0.07); font-size: 12px; color: var(--text-2);
  cursor: pointer; user-select: none; transition: border-color 0.15s ease, background 0.15s ease;
}
.token-chip:hover { border-color: rgba(96, 165, 250, 0.6); background: rgba(96, 165, 250, 0.13); }
.t-icon { color: #60a5fa; font-size: 12px; }
.t-text { color: var(--text-1); font-weight: 600; letter-spacing: 0.2px; white-space: nowrap; }
.t-gear {
  border: none; background: none; cursor: pointer; color: var(--text-3);
  font-size: 13px; line-height: 1; padding: 2px 5px; border-radius: 999px;
  transition: color 0.15s ease, background 0.15s ease;
}
.t-gear:hover { color: #60a5fa; background: rgba(96, 165, 250, 0.16); }
/* 单个「＋ 新建」按钮（下拉入口已合并进按钮内，无独立小箭头） */
.new-btn {
  font-weight: 650; font-size: 12.5px;
  padding: 0 16px !important; height: 28px !important;
  box-shadow: 0 0 18px rgba(74, 222, 128, 0.28);
  transition: box-shadow 0.15s ease;
}
.new-btn:hover { box-shadow: 0 0 24px rgba(74, 222, 128, 0.45); }

/* 弹窗 */
.form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.hint { font-size: 11px; color: var(--text-3); line-height: 1.6; }
.footer { display: flex; justify-content: flex-end; gap: 10px; }

/* 截止时间快捷选项 */
.due-quick { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 2px; }
.q-chip {
  font-size: 11px; padding: 3px 11px; border-radius: 999px; cursor: pointer;
  background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); color: var(--text-2);
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.q-chip:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.q-chip.on {
  color: var(--accent); border-color: rgba(74, 222, 128, 0.5);
  background: rgba(74, 222, 128, 0.12);
}

@media (max-width: 1440px) {
  .status-group { display: none; }
}
@media (max-width: 1100px) {
  .greet-sub { display: none; }
  .weather { display: none; }
}
</style>
