<script setup>
import { computed, onMounted, ref } from 'vue'
import { NButton, NColorPicker, NInput, NPopconfirm, NSelect, NSlider, NSwitch, useMessage } from 'naive-ui'
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

/* ─────────── 背景外观（自主设置） ─────────── */
const ap = computed(() => store.settings.appearance)
const activePreset = computed(() => s.value.bgPresets.find((p) => p.key === ap.value.preset))

/** 常用底色快捷选择 */
const BG_COLORS = [
  { name: '墨黑（默认）', value: '#070a08' },
  { name: '纯黑', value: '#000000' },
  { name: '深灰', value: '#111315' },
  { name: '深蓝', value: '#080d16' },
  { name: '深紫', value: '#0d0812' },
  { name: '深褐', value: '#120d08' },
  { name: '暗绿', value: '#06100b' },
]

async function setApp(patch) {
  try {
    await store.setAppearance(patch)
  } catch (err) {
    message.error('保存失败：' + err.message)
  }
}

function pickPreset(key) {
  setApp({ preset: key })
  const p = s.value.bgPresets.find((x) => x.key === key)
  message.success(`背景光晕已切换：${p?.name || key}`)
}

/* ── 壁纸：读取 → 压缩 → 应用 ── */
const wallInput = ref(null)

/** 等比压缩到 maxW 宽，避免超出 localStorage 配额 */
function compressImage(file, maxW = 2560, quality = 0.85) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('图片解析失败（格式不支持？）'))
      img.onload = () => {
        const scale = Math.min(1, maxW / (img.width || maxW))
        const w = Math.max(1, Math.round(img.width * scale))
        const h = Math.max(1, Math.round(img.height * scale))
        const cv = document.createElement('canvas')
        cv.width = w; cv.height = h
        const ctx = cv.getContext('2d')
        ctx.drawImage(img, 0, 0, w, h)
        // PNG 透明图保留 png，其余转 jpeg 压体积
        const isPng = /png$/i.test(file.type)
        resolve(cv.toDataURL(isPng ? 'image/png' : 'image/jpeg', quality))
      }
      img.src = reader.result
    }
    reader.readAsDataURL(file)
  })
}

async function onWallPick(e) {
  const file = e.target.files?.[0]
  e.target.value = ''            // 允许重复选同一文件
  if (!file) return
  if (!/^image\//.test(file.type)) { message.warning('请选择图片文件'); return }
  if (file.size > 20 * 1024 * 1024) { message.warning('图片过大（请选 20MB 以内）'); return }
  try {
    const dataUrl = await compressImage(file)
    await store.setWallpaper(dataUrl)
    const kb = Math.round(dataUrl.length / 1024)
    message.success(`壁纸已应用（约 ${kb} KB）`)
  } catch (err) {
    message.error(err.message)
  }
}

async function clearWall() {
  await store.setWallpaper('')
  message.success('已清除自定义壁纸')
}

async function resetAppearance() {
  await store.resetAppearance()
  message.success('背景外观已恢复默认')
}

/** 预览区样式：底色 + 壁纸 + 主光晕角度 */
const previewStyle = computed(() => {
  const a = ap.value
  const p = activePreset.value || s.value.bgPresets[0]
  const dim = Math.min(90, Math.max(0, a.wallpaperDim ?? 45)) / 100
  const layers = []
  layers.push(`radial-gradient(140px 90px at 20% 0%, ${p.glow[0]}, transparent 70%)`)
  layers.push(`radial-gradient(120px 80px at 95% 100%, ${p.glow[1]}, transparent 70%)`)
  if (a.wallpaper) layers.push(`linear-gradient(rgba(0,0,0,${dim}), rgba(0,0,0,${dim}))`)
  if (a.wallpaper) layers.push(`url("${a.wallpaper}")`)
  return {
    backgroundColor: a.bgColor || '#070a08',
    backgroundImage: layers.join(', '),
    backgroundSize: a.wallpaper ? 'auto, auto, auto, cover' : 'auto, auto',
    backgroundPosition: 'center',
  }
})

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
    </div>

    <div class="grid">
      <!-- ═══ 个性化：主题强调色 + 背景外观（合并为一张紧凑卡片）═══ -->
      <section class="col-12 card personal">
        <header class="card-head">
          <div>
            <div class="card-title">🎨 个性化外观 <span class="en">APPEARANCE</span></div>
            <div class="panel-sub">强调色、光晕配色、底色、网格、圆角与自定义壁纸——全部即时生效并保存</div>
          </div>
          <div class="head-ops">
            <NPopconfirm @positive-click="resetAppearance">
              <template #trigger><NButton size="tiny" quaternary>↺ 恢复默认</NButton></template>
              将光晕、底色、网格、圆角与壁纸全部恢复为出厂默认？
            </NPopconfirm>
          </div>
        </header>

        <div class="p-body">
          <!-- 左：全部控制项 -->
          <div class="p-ctrl">
            <!-- 主题强调色 -->
            <div class="p-block">
              <div class="p-block-head">
                <span class="p-block-title">主题强调色</span>
                <span class="p-block-hint">图表 / 进度条 / 状态点实时跟随</span>
              </div>
              <div class="accent-row">
                <button v-for="p in s.accentPresets" :key="p.value"
                        class="accent-btn" :class="{ on: s.accent === p.value }"
                        :title="p.name + ' ' + p.value"
                        @click="applyAccent(p.value, p.name)">
                  <i class="sw" :style="{ background: p.value, boxShadow: `0 0 12px ${p.value}` }" />
                  <span class="a-name">{{ p.name }}</span>
                  <em class="mono">{{ p.value }}</em>
                </button>
              </div>
            </div>

            <!-- 光晕配色 -->
            <div class="p-block">
              <div class="p-block-head">
                <span class="p-block-title">光晕配色</span>
                <span class="p-block-hint">{{ activePreset?.hint }}</span>
              </div>
              <div class="bg-presets">
                <button v-for="p in s.bgPresets" :key="p.key"
                        class="bg-preset" :class="{ on: ap.preset === p.key }"
                        :title="p.hint" @click="pickPreset(p.key)">
                  <i class="bg-dot" :style="{ background: p.glow[0], boxShadow: `0 0 10px ${p.glow[0]}` }" />
                  <i class="bg-dot sm" :style="{ background: p.glow[1] }" />
                  <span>{{ p.name }}</span>
                </button>
              </div>
            </div>

            <!-- 滑杆组 -->
            <div class="p-block">
              <div class="p-sliders">
                <div class="bg-slider-row">
                  <span class="bg-label">光晕强度</span>
                  <NSlider :value="ap.glow" :min="0" :max="160" :step="5" class="bg-slider"
                           @update:value="(v) => setApp({ glow: v })" />
                  <span class="bg-val mono">{{ ap.glow }}%</span>
                </div>
                <div class="bg-slider-row">
                  <span class="bg-label">网格纹理</span>
                  <NSlider :value="ap.grid" :min="0" :max="40" :step="2" class="bg-slider"
                           @update:value="(v) => setApp({ grid: v })" />
                  <span class="bg-val mono">{{ ap.grid }}%</span>
                </div>
                <div class="bg-slider-row">
                  <span class="bg-label">卡片圆角</span>
                  <NSlider :value="ap.radius" :min="8" :max="26" :step="1" class="bg-slider"
                           @update:value="(v) => setApp({ radius: v })" />
                  <span class="bg-val mono">{{ ap.radius }}px</span>
                </div>
                <div v-if="ap.wallpaper" class="bg-slider-row">
                  <span class="bg-label">壁纸压暗</span>
                  <NSlider :value="ap.wallpaperDim" :min="0" :max="90" :step="5" class="bg-slider"
                           @update:value="(v) => setApp({ wallpaperDim: v })" />
                  <span class="bg-val mono">{{ ap.wallpaperDim }}%</span>
                </div>
              </div>
            </div>

            <!-- 底色 + 壁纸 -->
            <div class="p-block">
              <div class="p-inline">
                <span class="bg-label">背景底色</span>
                <NColorPicker :value="ap.bgColor" :modes="['hex']" size="small" style="width: 112px"
                              :show-alpha="false" @update:value="(v) => setApp({ bgColor: v })" />
                <div class="bg-color-chips">
                  <button v-for="c in BG_COLORS" :key="c.value" class="bg-color-chip"
                          :class="{ on: ap.bgColor === c.value }" :title="c.name"
                          :style="{ background: c.value }" @click="setApp({ bgColor: c.value })" />
                </div>
                <span class="p-sep" />
                <input ref="wallInput" type="file" accept="image/*" style="display:none" @change="onWallPick" />
                <NButton size="tiny" secondary @click="wallInput?.click()">🖼 选择壁纸</NButton>
                <NButton v-if="ap.wallpaper" size="tiny" quaternary type="error" @click="clearWall">✕ 清除</NButton>
                <span class="p-block-hint">{{ ap.wallpaper ? '已应用（仅存本机）' : 'JPG/PNG，自动压缩' }}</span>
              </div>
            </div>

            <!-- 其他偏好 -->
            <div class="p-block">
              <div class="p-inline pref">
                <span class="bg-label">默认折叠侧边导航</span>
                <NSwitch v-model:value="store.sidebarCollapsed" size="small" />
                <span class="p-sep" />
                <span class="bg-label">天气城市</span>
                <NSelect :value="store.settings.weatherCity" :options="cityOptions" size="small"
                         style="width: 104px" @update:value="changeCity" />
              </div>
            </div>
          </div>

          <!-- 右：实时预览 -->
          <aside class="p-preview">
            <div class="p-block-head">
              <span class="p-block-title">实时预览</span>
              <span class="p-block-hint">壁纸仅存本机</span>
            </div>
            <div class="bvp" :style="previewStyle">
              <div class="bvp-sheen" :style="{ opacity: (ap.glow / 100) * 0.9 }" />
              <div class="bvp-grid" :style="{ opacity: ap.grid / 100 }" />
              <div class="bvp-top">
                <i class="bvp-dot" />
                <div class="bvp-bar w40" />
                <i class="bvp-pill" :style="{ background: s.accent }" />
              </div>
              <div class="bvp-card" :style="{ borderRadius: ap.radius + 'px' }">
                <div class="bvp-line w60" />
                <div class="bvp-line w90" />
                <div class="bvp-line w40" />
              </div>
              <div class="bvp-row">
                <div class="bvp-card sm" :style="{ borderRadius: ap.radius + 'px' }">
                  <div class="bvp-line w70" />
                  <div class="bvp-line w50" />
                </div>
                <div class="bvp-card sm" :style="{ borderRadius: ap.radius + 'px' }">
                  <div class="bvp-line w80" />
                  <div class="bvp-line w30" />
                </div>
              </div>
            </div>
          </aside>
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

/* ─────────── 个性化外观（强调色 + 背景外观 合并）─────────── */
.personal { padding-bottom: 16px; }
.head-ops { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

/* 左右两栏：控制项（自适应） + 预览（固定窄栏） */
.p-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(206px, 258px);
  gap: 16px;
  align-items: stretch;      /* 两栏等高：预览区自动填满，避免右侧留白 */
}
.p-ctrl { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.p-block {
  border: 1px solid var(--border); border-radius: 10px;
  padding: 9px 12px; background: rgba(255, 255, 255, 0.014);
}
.p-block-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 10px; margin-bottom: 8px;
}
.p-block-title { font-size: 11.5px; color: var(--text-2); font-weight: 600; white-space: nowrap; }
.p-block-hint { font-size: 10px; color: var(--text-3); text-align: right; }

.p-inline { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.p-inline.pref { gap: 10px; }
.p-sep { width: 1px; height: 16px; background: var(--border); flex-shrink: 0; }
.bg-color-chips { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }

.accent-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 8px; }
.accent-btn {
  display: flex; align-items: center; gap: 7px; cursor: pointer;
  padding: 7px 10px; border-radius: 9px; background: transparent;
  border: 1px solid var(--border); color: var(--text-2); font-size: 11.5px;
  text-align: left; min-width: 0;
}
.accent-btn:hover { border-color: #3a3a3a; color: var(--text-1); }
.accent-btn.on { border-color: var(--accent); background: rgba(74, 222, 128, 0.07); color: var(--text-1); }
.accent-btn em { margin-left: auto; font-style: normal; font-size: 9.5px; color: var(--text-3); }
.accent-btn.on em { color: var(--text-2); }
.accent-btn .a-name { white-space: nowrap; }
.sw { width: 12px; height: 12px; border-radius: 50%; display: inline-block; flex-shrink: 0; }

.bg-presets { display: grid; grid-template-columns: repeat(auto-fit, minmax(104px, 1fr)); gap: 7px; }
.bg-preset {
  display: flex; align-items: center; gap: 6px; cursor: pointer;
  border: 1px solid var(--border); border-radius: 9px; padding: 7px 9px;
  background: transparent; color: var(--text-2); font-size: 11px; text-align: left; min-width: 0;
}
.bg-preset:hover { border-color: #3a3a3a; color: var(--text-1); }
.bg-preset.on { border-color: var(--accent); background: rgba(74, 222, 128, 0.07); color: var(--text-1); }
.bg-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.bg-dot.sm { width: 6px; height: 6px; opacity: 0.75; }

.p-sliders { display: flex; flex-direction: column; gap: 2px; }
.bg-slider-row { display: flex; align-items: center; gap: 10px; padding: 2px 0; }
.bg-label { font-size: 11px; color: var(--text-2); white-space: nowrap; flex-shrink: 0; }
.bg-slider { flex: 1; min-width: 80px; }
.bg-val { font-size: 10px; color: var(--text-3); width: 40px; text-align: right; flex-shrink: 0; }

.bg-color-chip {
  width: 19px; height: 19px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border-strong); padding: 0; flex-shrink: 0;
}
.bg-color-chip.on { outline: 2px solid var(--accent); outline-offset: 1px; }

/* 预览栏 */
.p-preview { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.bvp {
  position: relative; overflow: hidden; flex: 1; min-height: 200px;
  border: 1px solid var(--border); border-radius: 12px;
  display: flex; flex-direction: column; justify-content: center; gap: 9px; padding: 13px;
  background-size: cover; background-position: center;
}
.bvp-sheen { position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(150px 100px at 20% 0%, rgba(74, 222, 128, 0.25), transparent 70%); }
.bvp-grid { position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
  background-size: 24px 24px; }
.bvp-top { position: relative; z-index: 1; display: flex; align-items: center; gap: 6px; }
.bvp-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 8px var(--accent); flex-shrink: 0; }
.bvp-bar { height: 4px; border-radius: 2px; background: rgba(255,255,255,0.16); }
.bvp-pill { width: 26px; height: 11px; border-radius: 999px; margin-left: auto; flex-shrink: 0; opacity: .9; }
.bvp-card {
  position: relative; z-index: 1; padding: 7px 9px; display: flex; flex-direction: column; gap: 5px;
  background: var(--card); border: 1px solid var(--border);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
}
.bvp-row { position: relative; z-index: 1; display: flex; gap: 7px; }
.bvp-row .bvp-card { flex: 1; min-width: 0; }
.bvp-card.sm { width: 100%; }
.bvp-line { height: 4px; border-radius: 3px; background: rgba(255, 255, 255, 0.14); }
.bvp-line.w30 { width: 30%; } .bvp-line.w40 { width: 40%; } .bvp-line.w50 { width: 50%; }
.bvp-line.w60 { width: 60%; } .bvp-line.w70 { width: 70%; }
.bvp-line.w80 { width: 80%; } .bvp-line.w90 { width: 90%; }

@media (max-width: 1180px) {
  .p-body { grid-template-columns: 1fr; }
  .bvp { min-height: 168px; }
  .p-block-head { flex-wrap: wrap; }
  .p-block-hint { text-align: left; }
}

.divider { height: 1px; background: var(--border); margin: 16px 0; }
.set-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 0; border-bottom: 1px dashed var(--border); }
.set-line:last-child { border-bottom: none; }
.s-title { font-size: 13px; }
.hint { font-size: 10.5px; color: var(--text-3); margin-top: 10px; line-height: 1.7; }
.hint em { color: var(--accent); font-style: normal; }

.src-row { display: flex; align-items: center; gap: 14px; padding: 9px 0; border-bottom: 1px dashed var(--border); }.src-row .label-3 { width: 82px; flex-shrink: 0; }
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
