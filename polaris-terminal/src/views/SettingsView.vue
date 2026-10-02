<script setup>
import { computed, onMounted, ref } from 'vue'
import { NButton, NInput, NPopconfirm, NSelect, NSwitch, useMessage } from 'naive-ui'
import { coursesApi, healthApi, tasksApi } from '../api'
import { store } from '../store'
import { downloadCsv } from '../utils/export'

const message = useMessage()
const s = computed(() => store.settings)

const cityOptions = ['武汉', '北京', '上海', '广州', '成都', '西安', '南京', '滨州'].map((c) => ({ label: c, value: c }))

const shortcuts = [
  { keys: 'Ctrl / ⌘ + K', desc: '唤起 / 聚焦 AI 助手' },
  { keys: 'Enter', desc: 'AI 输入框发送消息' },
  { keys: '点击卡片条目', desc: '总览 DDL 直接标记完成' },
  { keys: '拖动 AI 标题栏', desc: '移动助手窗口位置' },
  { keys: '« 收起', desc: '侧边导航折叠为图标模式' },
]

function applyAccent(color, name) {
  store.setAccent(color)
  message.success(`已切换主题强调色并已同步到账号配置：${name}`)
}

/** 连接测试：真实拉取后端运行态 */
async function testConnection() {
  try {
    await store.refresh()
    const rt = store.runtime
    message.success(
      `连接正常 · 数据库 ${rt?.database?.engine} · 缓存 ${rt?.cache?.mode} · AI ${rt?.ai?.mode}`,
    )
  } catch (err) {
    message.error(`连接失败：${err.message}`)
  }
}

async function changeCity(city) {
  await store.setWeatherCity(city)
  message.success(`天气城市已更新为 ${city}`)
}

/* ── 数据备份管理 ── */
const backups = ref([])
const backupLoading = ref(false)
async function loadBackups() {
  backupLoading.value = true
  try { backups.value = await store.listBackups() }
  catch (err) { message.error('备份列表加载失败：' + err.message) }
  finally { backupLoading.value = false }
}
async function createBackup() {
  try {
    const record = await store.createBackup()
    message.success(`备份已生成：${record.filename}（${record.size_kb} KB · ${record.tables.length} 张表）`)
    await loadBackups()
  } catch (err) {
    message.error(err.message)
  }
}
async function deleteBackup(b) {
  try {
    await store.removeBackup(b.id)
    message.success('备份已删除')
    await loadBackups()
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}
onMounted(loadBackups)

/* ── 数据导出（真实接口拉全量 → CSV）── */
const exporting = ref('')
async function exportData(kind) {
  exporting.value = kind
  try {
    if (kind === 'courses') {
      const data = await coursesApi.list({})
      const items = data?.items || []
      const rows = []
      for (const c of items) {
        for (const sc of c.schedules || []) {
          rows.push([c.name, c.teacher || '—', sc.weekday_cn || `周${sc.weekday}`,
                     `${sc.start_time}-${sc.end_time}`, sc.weeks || '—', sc.week_type || '全周',
                     sc.location || c.location || '—', c.credit ?? 0, c.course_type || '必修'])
        }
      }
      if (!rows.length) { message.warning('暂无课程可导出'); return }
      await downloadCsv('课程表.csv', ['课程', '教师', '星期', '时间', '周次', '单双周', '教室', '学分', '类型'], rows)
    } else if (kind === 'tasks') {
      const data = await tasksApi.list({ limit: 500, order: 'priority' })
      const rows = (data?.items || []).map((t) => [
        t.title, t.status === 'done' ? '已完成' : '待办', t.priority, t.category || '—',
        (t.due_at || '').replace('T', ' ') || '—', t.estimate_minutes || 0, t.description || ''])
      if (!rows.length) { message.warning('暂无事项可导出'); return }
      await downloadCsv('事项备忘.csv', ['标题', '状态', '优先级', '分类', '截止时间', '预计分钟', '描述'], rows)
    } else if (kind === 'kaoyan') {
      const subs = store.kaoyan.subjects
      if (!subs.length) { message.warning('尚未录入考研目标成绩'); return }
      await downloadCsv('考研成绩.csv', ['科目', '当前分', '目标分', '满分', '分数线', '差距', '达成率%'],
        subs.map((x) => [x.name, x.current, x.target, x.max ?? 100, x.line ?? '—', x.gap, x.rate]))
    } else if (kind === 'finance') {
      const recs = store.finance.records
      if (!recs.length) { message.warning('暂无账单流水可导出'); return }
      await downloadCsv('财务流水.csv', ['日期', '类型', '分类', '项目', '金额', '学习支出', '支付方式'],
        recs.map((r) => [r.dateFull, r.type === 'income' ? '收入' : '支出', r.cat, r.item,
                         r.amount, r.study ? '是' : '否', r.payment || '—']))
    } else if (kind === 'health') {
      const data = await healthApi.records(90)
      const items = data?.items || []
      if (!items.length) { message.warning('暂无健康记录可导出'); return }
      await downloadCsv('健康记录.csv', ['日期', '睡眠(h)', '运动(min)', '久坐(min)', '饮水(ml)', '步数', '体重(kg)', '心情', '就寝', '起床', '备注'],
        items.map((x) => [x.date, x.sleep_hours, x.exercise_minutes, x.sedentary_minutes,
                          x.water_ml, x.steps, x.weight ?? '—', x.mood ?? '—',
                          x.bed_time || '—', x.wake_time || '—', x.note || '']))
    }
    message.success('导出完成，文件已开始下载')
  } catch (err) {
    message.error('导出失败：' + err.message)
  } finally {
    exporting.value = ''
  }
}

/* ── 微信订阅推送 ── */
const wx = computed(() => store.wx)
const wxStatus = computed(() => wx.value.status || {})
const wxQuotaItems = computed(() => (wx.value.quota?.items || []))
const KIND_LABEL = { ddl: '事项 DDL 提醒', class: '上课提醒' }
const pushBusy = ref('')
const pushing = ref(false)
const scanning = ref(false)

async function testPush(kind) {
  pushBusy.value = kind
  pushing.value = true
  try {
    const r = await store.wechatTestPush(kind)
    if (r.status === 'success' || r.sent) message.success(`${KIND_LABEL[kind]}：已发送（mock 模式仅写日志）`)
    else message.warning(`${KIND_LABEL[kind]}：${r.status || '未发送'} · ${r.errmsg || '详见推送日志'}`)
  } catch (err) {
    message.error('推送失败：' + err.message)
  } finally {
    pushing.value = false
    pushBusy.value = ''
  }
}
async function runScan() {
  scanning.value = true
  try {
    const r = await store.wechatScan()
    message.success(`扫描完成（${r.at}）：DDL ${r.ddl?.sent ?? 0} 条 · 上课 ${r.class?.sent ?? 0} 条`)
  } catch (err) {
    message.error('扫描失败：' + err.message)
  } finally {
    scanning.value = false
  }
}
async function grantQuota(kind) {
  try {
    await store.wechatGrant(kind, 10)
    message.success(`已为「${KIND_LABEL[kind]}」模拟上报 10 次订阅授权（实际由小程序授权后自动上报）`)
  } catch (err) {
    message.error('上报失败：' + err.message)
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>系统设置</h2>
      <span class="sub mono">SETTINGS · 个性化 / 数据源 / 推送 / 导出 / 关于</span>
    </div>

    <div class="grid">
      <!-- 个性化 -->
      <section class="col-6 card">
        <header class="card-head"><div class="card-title">◐ 主题强调色 <span class="en">ACCENT</span></div></header>
        <div class="accent-row">
          <button
            v-for="p in s.accentPresets" :key="p.value"
            class="accent-btn" :class="{ on: s.accent === p.value }"
            @click="applyAccent(p.value, p.name)"
          >
            <i class="sw" :style="{ background: p.value, boxShadow: `0 0 12px ${p.value}` }" />
            <span>{{ p.name }}</span>
            <em class="mono">{{ p.value }}</em>
          </button>
        </div>
        <div class="hint mono">切换后图表、进度条、状态点会实时跟随（CSS 变量 + ECharts 重绘），并同步保存到你的账号配置</div>

        <div class="divider" />

        <div class="set-line">
          <div>
            <div class="s-title">默认折叠侧边导航</div>
            <div class="label-3">适合小屏 / 专注模式</div>
          </div>
          <NSwitch v-model:value="store.sidebarCollapsed" />
        </div>
        <div class="set-line">
          <div>
            <div class="s-title">天气城市</div>
            <div class="label-3">顶部状态栏展示，保存到账号配置</div>
          </div>
          <NSelect :value="store.settings.weatherCity" :options="cityOptions" size="small" style="width: 130px" @update:value="changeCity" />
        </div>
      </section>

      <!-- 数据源与备份 -->
      <section class="col-6 card">
        <header class="card-head">
          <div class="card-title">⇄ 数据源与备份 <span class="en">DATA SOURCE</span></div>
          <span class="chip chip-accent">真实接口</span>
        </header>
        <div class="src-row">
          <span class="label-3">当前模式</span>
          <span class="mono v ok">{{ s.dataSource }}</span>
        </div>
        <div class="src-row">
          <span class="label-3">数据库</span>
          <span class="mono v">{{ s.backendUrl }}</span>
        </div>
        <div class="src-row">
          <span class="label-3">版本</span>
          <span class="mono v">{{ s.version }}</span>
        </div>
        <div class="btn-row">
          <NButton size="small" type="primary" ghost @click="testConnection">测试连接</NButton>
          <NButton size="small" quaternary @click="createBackup">立即备份数据</NButton>
          <NButton size="small" quaternary :loading="backupLoading" @click="loadBackups">刷新列表</NButton>
        </div>
        <div v-if="backups.length" class="bk-list">
          <div v-for="b in backups.slice(0, 5)" :key="b.id" class="bk-row">
            <span class="mono c3">{{ (b.created_at || '').slice(5, 16) }}</span>
            <span class="bk-name">{{ b.filename }}</span>
            <span class="chip mono">{{ b.size_kb }} KB</span>
            <span class="chip">{{ b.tables.length }} 表</span>
            <NPopconfirm @positive-click="deleteBackup(b)">
              <template #trigger><button class="op-btn del" title="删除备份">✕</button></template>
              删除备份文件 {{ b.filename }}？
            </NPopconfirm>
          </div>
        </div>
        <div v-else class="bk-empty mono c3">暂无备份 · 点击「立即备份数据」生成用户数据快照</div>
      </section>

      <!-- 数据导出 -->
      <section class="col-6 card">
        <header class="card-head"><div class="card-title">⬇ 数据导出 <span class="en">EXPORT CSV</span></div></header>
        <div class="exp-grid">
          <button class="exp-btn" :disabled="!!exporting" @click="exportData('courses')">
            <b>▤ 课程表</b><span class="c3">{{ store.weekTimetable.totalClasses }} 门本周安排 · 导出全部排课</span>
          </button>
          <button class="exp-btn" :disabled="!!exporting" @click="exportData('tasks')">
            <b>☑ 事项备忘</b><span class="c3">{{ store.notes.length }} 条事项 · 含状态与截止时间</span>
          </button>
          <button class="exp-btn" :disabled="!!exporting" @click="exportData('kaoyan')">
            <b>✧ 考研成绩</b><span class="c3">{{ store.kaoyan.subjects.length }} 科分数与差距分析</span>
          </button>
          <button class="exp-btn" :disabled="!!exporting" @click="exportData('finance')">
            <b>¥ 财务流水</b><span class="c3">{{ store.finance.records.length }} 条账单（近 60 条）</span>
          </button>
          <button class="exp-btn" :disabled="!!exporting" @click="exportData('health')">
            <b>♥ 健康记录</b><span class="c3">近 90 天睡眠/运动/饮水/体重全量</span>
          </button>
        </div>
        <div class="hint mono">CSV 带 BOM，Excel / WPS 双击直接打开不乱码；课程表与健康记录会实时拉取后端全量数据</div>
      </section>

      <!-- 微信订阅推送 -->
      <section class="col-6 card">
        <header class="card-head">
          <div class="card-title">✉ 微信订阅推送 <span class="en">WECHAT PUSH</span></div>
          <span class="chip" :class="wxStatus.configured ? 'chip-accent' : 'chip-yellow'">
            {{ wxStatus.mode === 'live' ? '已配置 · live' : '未配置 · mock（只写日志）' }}
          </span>
        </header>
        <div v-if="wxStatus.hint" class="wx-hint mono">{{ wxStatus.hint }}</div>

        <div class="quota-row">
          <div v-for="q in wxQuotaItems" :key="q.kind" class="quota-card">
            <div class="q-kind">{{ KIND_LABEL[q.kind] || q.kind }}</div>
            <div class="q-nums mono">
              剩余 <b :class="q.remaining > 0 ? 'ok' : 'warn'">{{ q.remaining }}</b>
              / 已用 {{ q.used_total }} / 累计 {{ q.granted_total }}
            </div>
            <div class="q-ops">
              <NButton size="tiny" type="primary" ghost :loading="pushing && pushBusy === q.kind" @click="testPush(q.kind)">测试推送</NButton>
              <NButton size="tiny" quaternary @click="grantQuota(q.kind)">＋10 额度</NButton>
            </div>
          </div>
        </div>

        <div class="wx-line">
          <span class="label-3">定时扫描</span>
          <span class="mono c3">{{ wxStatus.scheduler_enabled ? '已启用（到期 DDL + 上课前提醒）' : '未启用' }} · 提前 DDL {{ wxStatus.ahead_minutes?.ddl ?? '—' }}min / 上课 {{ wxStatus.ahead_minutes?.class ?? '—' }}min</span>
          <NButton size="tiny" type="info" ghost :loading="scanning" @click="runScan">立即扫描</NButton>
        </div>
        <div class="wx-line">
          <span class="label-3">OpenID 绑定</span>
          <span class="chip" :class="wx.quota?.wx_openid_bound ? 'chip-accent' : 'chip-red'">{{ wx.quota?.wx_openid_bound ? '已绑定' : '未绑定（需小程序登录）' }}</span>
        </div>

        <div class="log-title mono">最近推送日志（{{ (wx.logs || []).length }} 条）</div>
        <div class="wx-logs">
          <div v-for="l in wx.logs || []" :key="l.id" class="wl-row">
            <span class="mono c3">{{ (l.created_at || '').slice(5, 16) }}</span>
            <span class="chip">{{ KIND_LABEL[l.kind] || l.kind }}</span>
            <span class="chip" :class="l.status === 'success' ? 'chip-accent' : l.status === 'skipped' ? '' : 'chip-red'">{{ l.status }}</span>
            <span class="wl-msg c3">{{ l.errmsg || l.payload?.thing?.value || l.page || '—' }}</span>
          </div>
          <div v-if="!(wx.logs || []).length" class="c3 mono wl-empty">暂无推送记录</div>
        </div>
      </section>

      <!-- 快捷键 -->
      <section class="col-6 card">
        <header class="card-head"><div class="card-title">⌨ 快捷键 <span class="en">SHORTCUTS</span></div></header>
        <div v-for="k in shortcuts" :key="k.keys" class="key-row">
          <span class="mono keys">{{ k.keys }}</span>
          <span class="label-3">{{ k.desc }}</span>
        </div>
      </section>

      <!-- 关于 -->
      <section class="col-6 card">
        <header class="card-head"><div class="card-title">✦ 关于 <span class="en">ABOUT</span></div></header>
        <div class="about">
          <div class="logo-row">
            <span class="big-star">✦</span>
            <div>
              <div class="an">北极星 · 个人战略终端</div>
              <div class="mono av">{{ s.version }}</div>
            </div>
          </div>
          <p class="desc">
            面向个人学习 / 工作 / 生活的一体化战略终端：课程表、事项备忘、空教室预测、考研规划、
            知识整理、资产财务、健康管理七大模块 + 全局 AI 助手 + 微信订阅推送。
          </p>
          <div class="tech">
            <span class="chip chip-accent">Vue 3</span>
            <span class="chip chip-blue">Vite</span>
            <span class="chip chip-yellow">Naive UI</span>
            <span class="chip chip-red">ECharts</span>
            <span class="chip">FastAPI + MySQL</span>
            <span class="chip">HarmonyOS 小程序</span>
          </div>
          <div class="hint mono">数据与状态：{{ store.notes.length }} 条备忘 · {{ store.knowledgeDocs.length }} 篇文档 · {{ store.newsFeed.length }} 条快讯</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; min-width: 0; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; gap: 10px; }

.accent-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.accent-btn {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 10px 12px; border-radius: 10px; background: transparent;
  border: 1px solid var(--border); color: var(--text-2); font-size: 12.5px;
}
.accent-btn:hover { border-color: #3a3a3a; color: var(--text-1); }
.accent-btn.on { border-color: var(--accent); background: rgba(74, 222, 128, 0.07); color: var(--text-1); }
.accent-btn em { margin-left: auto; font-style: normal; font-size: 10px; color: var(--text-3); }
.sw { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }

.divider { height: 1px; background: var(--border); margin: 16px 0; }
.set-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 0; border-bottom: 1px dashed var(--border); }
.set-line:last-child { border-bottom: none; }
.s-title { font-size: 13px; }
.hint { font-size: 10.5px; color: var(--text-3); margin-top: 10px; line-height: 1.7; }
.hint em { color: var(--accent); font-style: normal; }

.src-row { display: flex; align-items: center; gap: 14px; padding: 9px 0; border-bottom: 1px dashed var(--border); }
.src-row .label-3 { width: 82px; flex-shrink: 0; }
.v { font-size: 11.5px; color: var(--text-2); word-break: break-all; }
.v.ok { color: var(--accent); }
.btn-row { display: flex; gap: 10px; margin-top: 14px; }

.bk-list { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 8px; max-height: 150px; overflow-y: auto; }
.bk-row { display: flex; align-items: center; gap: 8px; font-size: 11px; padding: 4px 0; }
.bk-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bk-empty { font-size: 10.5px; margin-top: 10px; }
.op-btn {
  width: 22px; height: 22px; border-radius: 6px; cursor: pointer; flex-shrink: 0;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 10px;
}
.op-btn:hover { color: var(--red); border-color: rgba(248, 113, 113, 0.4); }

.exp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.exp-btn {
  display: flex; flex-direction: column; gap: 4px; text-align: left; cursor: pointer;
  padding: 11px 13px; border-radius: 10px; background: transparent;
  border: 1px solid var(--border); color: var(--text-1); font-size: 13px;
}
.exp-btn:hover:not(:disabled) { border-color: var(--accent); background: rgba(74, 222, 128, 0.05); }
.exp-btn:disabled { opacity: 0.5; cursor: wait; }
.exp-btn .c3 { font-size: 10.5px; }

.wx-hint { font-size: 10.5px; color: var(--yellow); background: rgba(250, 204, 21, 0.06); border: 1px dashed rgba(250, 204, 21, 0.35); border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; line-height: 1.6; }
.quota-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.quota-card { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
.q-kind { font-size: 12.5px; margin-bottom: 4px; }
.q-nums { font-size: 11px; color: var(--text-3); }
.q-nums b { font-size: 15px; }
.q-nums b.ok { color: var(--accent); }
.q-nums b.warn { color: var(--red); }
.q-ops { display: flex; gap: 8px; margin-top: 8px; }
.wx-line { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px dashed var(--border); font-size: 12px; }
.wx-line .label-3 { width: 72px; flex-shrink: 0; }
.log-title { font-size: 10.5px; color: var(--text-3); margin: 10px 0 4px; }
.wx-logs { max-height: 150px; overflow-y: auto; }
.wl-row { display: flex; align-items: center; gap: 8px; font-size: 11px; padding: 4px 0; border-bottom: 1px dashed rgba(42, 42, 42, 0.5); }
.wl-msg { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wl-empty { font-size: 10.5px; padding: 8px 0; }

.key-row { display: flex; align-items: center; gap: 14px; padding: 8px 0; border-bottom: 1px dashed var(--border); }
.key-row:last-child { border-bottom: none; }
.keys {
  min-width: 132px; font-size: 11px; color: var(--accent);
  border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; text-align: center;
  background: rgba(74, 222, 128, 0.05);
}

.logo-row { display: flex; align-items: center; gap: 14px; }
.big-star { font-size: 30px; color: var(--accent); text-shadow: 0 0 20px var(--accent); }
.an { font-size: 15px; font-weight: 700; }
.av { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.desc { color: var(--text-2); font-size: 12.5px; line-height: 1.85; margin: 14px 0; }
.tech { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
