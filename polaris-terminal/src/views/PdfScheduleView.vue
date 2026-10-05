<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NDatePicker, NInput, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'

const message = useMessage()
const ps = computed(() => store.pdfSchedule)

/* ── 上传 ── */
const fileInput = ref(null)
const dragOver = ref(false)
function pickFiles() { fileInput.value?.click() }
async function onFiles(e) {
  const files = Array.from(e.target?.files || [])
  if (fileInput.value) fileInput.value.value = ''
  await doUpload(files)
}
async function onDrop(e) {
  dragOver.value = false
  const files = Array.from(e.dataTransfer?.files || []).filter((f) => /\.pdf$/i.test(f.name))
  await doUpload(files)
}
async function doUpload(files) {
  if (!files.length) return
  const bad = files.find((f) => !/\.pdf$/i.test(f.name))
  if (bad) { message.error(`「${bad.name}」不是 PDF 文件，已忽略`); files.splice(files.indexOf(bad), 1) }
  if (!files.length) return
  if (files.length > 10) { message.error('单次最多上传 10 个文件'); return }
  try {
    const r = await store.uploadPdfSchedules(files)
    const failed = (r.items || []).filter((x) => x.status === 'failed')
    if (r.succeeded && !failed.length) message.success(`解析成功 ${r.succeeded} 个文件`)
    else if (r.succeeded) message.warning(`成功 ${r.succeeded} 个，失败 ${failed.length} 个，详见上传记录`)
    else message.error('全部解析失败，请查看下方错误提示与处理建议')
  } catch (err) {
    message.error('上传失败：' + err.message)
  }
}

/* ── 筛选 ── */
const DAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/** 解析模式 → 中文（不再直接显示 image_only 之类的内部标识） */
const MODE_LABEL = {
  grid: '网格表格',
  list: '明细清单',
  text: '文本解析',
  image_only: '图片扫描件',
  vision: 'AI 视觉识别',
  ai: 'AI 识别',
  mixed: '文本+图片',
}

/** 失败原因标题（按模式给出更准确的描述） */
const ERROR_TITLE = {
  image_only: '这是图片扫描件，需要 AI 视觉识别',
  vision: 'AI 视觉识别未成功',
  text: '未识别到课表内容',
}

function gotoExcel() {
  message.info('可在「课程表 → 导入个人课表 Excel」，或到「空教室」页导入教室课表 Excel')
}

function gotoClassroom() {
  window.location.hash = ''
  window.history.pushState({}, '', '/classroom')
  window.dispatchEvent(new PopStateEvent('popstate'))
}
const filters = ref({ room_no: null, weekday: null, week: null, day: null, course_type: null, keyword: '' })
const roomOptions = computed(() => (ps.value.options.rooms || []).map((r) => ({ label: r, value: r })))
const typeOptions = computed(() => (ps.value.options.course_types || []).map((t) => ({ label: t, value: t })))
const weekOptions = computed(() => {
  const cur = ps.value.currentWeek || 5
  return Array.from({ length: 20 }, (_, i) => i + 1).map((w) => ({
    label: w === cur ? `第 ${w} 周（当前）` : `第 ${w} 周`, value: w,
  }))
})
let kwTimer = null
function reload() {
  const f = filters.value
  const params = {}
  if (f.room_no) params.room_no = f.room_no
  if (f.weekday) params.weekday = f.weekday
  if (f.week) params.week = f.week
  if (f.course_type) params.course_type = f.course_type
  if (f.keyword) params.keyword = f.keyword
  if (f.day) params.day = new Date(f.day).toISOString().slice(0, 10)
  store.loadPdfSchedule(params).catch((err) => message.error('加载失败：' + err.message))
}
watch(filters, () => { clearTimeout(kwTimer); kwTimer = setTimeout(reload, 250) }, { deep: true })
onMounted(() => reload())

/* ── 周课表网格（星期 × 节次）── */
const SECTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
const PALETTE = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf', '#fb923c', '#38bdf8']
const grid = computed(() => {
  const cells = {}
  for (const e of ps.value.entries || []) {
    for (let s = e.start_section; s <= e.end_section; s++) {
      if (s > 12) continue
      const key = `${e.weekday}-${s}`
      if (!cells[key]) cells[key] = []
      if (s === e.start_section) cells[key].push(e)
      else if (!cells[key].some((x) => x.id === e.id)) cells[key].push({ ...e, spanned: true })
    }
  }
  return cells
})
function colorOf(name) {
  let h = 0
  for (const ch of name || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}
const weekFilterOn = computed(() => !!filters.value.week || !!filters.value.day)

async function removeUpload(id) {
  try {
    await store.removePdfSchedule(id)
    message.success('已删除')
  } catch (err) { message.error('删除失败：' + err.message) }
}
function fmtSize(n) {
  if (!n) return '—'
  return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB'
}
</script>

<template>
  <div class="pdf-schedule">
    <div class="pdf-head">
      <span class="spacer" />
      <input ref="fileInput" type="file" accept=".pdf" multiple style="display:none" @change="onFiles" />
      <NButton size="small" type="primary" ghost :loading="ps.uploading" @click="pickFiles">⬆ 上传 PDF 课表</NButton>
    </div>

    <!-- 上传区 -->
    <div
      class="drop-zone" :class="{ over: dragOver }"
      @click="pickFiles" @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false" @drop.prevent="onDrop"
    >
      <div class="dz-ico">⬆</div>
      <div class="dz-text">
        点击或拖拽 <b>PDF 教室课表</b> 到此处（支持多选，单个 ≤ 20MB，最多 10 个）
      </div>
      <div class="dz-hint mono">自动识别：文本表格（网格 / 明细清单）；图片扫描件走 AI 视觉识别</div>
    </div>

    <!-- 上传记录 -->
    <section class="card" style="margin: 16px 0">
      <header class="card-head">
        <div class="card-title">☰ 上传与解析记录 <span class="en">PARSE LOG</span></div>
        <span class="chip">{{ (ps.uploads || []).length }} 条</span>
      </header>
      <div v-if="!ps.uploads.length" class="empty-note">暂无上传记录，请先上传 PDF 课表</div>
      <div v-for="u in ps.uploads" :key="u.id" class="up-row">
        <div class="up-main">
          <div class="up-name">
            {{ u.filename }}
            <span class="chip" :class="u.status === 'failed' ? 'chip-red' : u.status === 'partial' ? 'chip-yellow' : 'chip-accent'">
              {{ u.status_label }}
            </span>
            <span v-if="u.room_no" class="chip mono">{{ u.room_no }}</span>
            <span v-if="u.semester" class="chip">{{ u.semester }}</span>
          </div>
          <div class="up-meta mono">
            {{ fmtSize(u.file_size) }} · 模式 {{ MODE_LABEL[u.parse_mode] || u.parse_mode || '—' }} ·
            条目 {{ u.entry_count }} ·
            置信度 {{ Math.round((u.confidence || 0) * 100) }}% · {{ u.created_at }}
          </div>

          <!-- 失败原因：完整可读，不截断 -->
          <div v-if="u.error" class="up-error">
            <span class="ue-ico">⚠</span>
            <div class="ue-body">
              <div class="ue-title">{{ ERROR_TITLE[u.parse_mode] || '解析失败' }}</div>
              <div class="ue-text">{{ u.error }}</div>
            </div>
          </div>

          <!-- 处理建议：逐条列出，可操作 -->
          <div v-if="u.suggestions && u.suggestions.length" class="up-sug-wrap">
            <div class="us-title mono">可以这样处理：</div>
            <ul class="up-sug">
              <li v-for="(s, i) in u.suggestions" :key="i">{{ s }}</li>
            </ul>
          </div>

          <!-- 失败项的快捷补救入口 -->
          <div v-if="u.status === 'failed'" class="up-ops">
            <NButton size="tiny" secondary @click="pickFiles">↻ 换个文件重传</NButton>
            <NButton size="tiny" quaternary @click="gotoExcel">▤ 改用 Excel 教室课表导入</NButton>
            <NButton size="tiny" quaternary @click="gotoClassroom">🏫 去空教室页导入</NButton>
          </div>
        </div>
        <NPopconfirm @positive-click="removeUpload(u.id)">
          <template #trigger><NButton size="tiny" quaternary type="error">删除</NButton></template>
          将同时删除该文件解析出的 {{ u.entry_count }} 条课程记录，确认？
        </NPopconfirm>
      </div>
    </section>

    <!-- 筛选 -->
    <div class="filter-bar card">
      <NSelect v-model:value="filters.room_no" size="small" class="f-item" clearable
               placeholder="教室" :options="roomOptions" />
      <NSelect v-model:value="filters.weekday" size="small" class="f-item" clearable
               placeholder="星期" :options="DAY_CN.map((d, i) => ({ label: d, value: i + 1 }))" />
      <NSelect v-model:value="filters.week" size="small" class="f-item" clearable
               placeholder="教学周" :options="weekOptions" />
      <NDatePicker v-model:value="filters.day" size="small" class="f-item" type="date" clearable
                   placeholder="按日期" />
      <NSelect v-model:value="filters.course_type" size="small" class="f-item" clearable
               placeholder="课程类型" :options="typeOptions" />
      <NInput v-model:value="filters.keyword" size="small" class="f-item f-kw" clearable
              placeholder="课程 / 教师 / 班级关键词" />
      <span class="spacer" />
      <span class="chip mono">共 {{ (ps.entries || []).length }} 条</span>
      <span v-if="ps.currentWeek" class="chip">当前第 {{ ps.currentWeek }} 周</span>
    </div>

    <div class="grid" style="margin-top: 16px">
      <!-- 周课表网格 -->
      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">▤ 课表网格 <span class="en">WEEKLY GRID · 星期 × 节次</span></div>
          <span v-if="weekFilterOn" class="chip chip-accent">已按周次过滤（灰色虚线=该周无课）</span>
        </header>
        <div v-if="!ps.entries.length" class="empty-note">
          {{ ps.loading ? '加载中…' : '当前筛选条件下暂无课程。上传 PDF 后自动展示。' }}
        </div>
        <div v-else class="tt-grid" :style="{ gridTemplateColumns: `52px repeat(7, 1fr)` }">
          <div class="tt-corner mono"></div>
          <div v-for="d in DAY_CN" :key="d" class="tt-day mono">{{ d }}</div>
          <template v-for="s in SECTIONS" :key="s">
            <div class="tt-sec mono">第{{ s }}节</div>
            <div v-for="w in 7" :key="w" class="tt-cell">
              <div
                v-for="e in (grid[`${w}-${s}`] || [])" :key="e.id"
                class="tt-block" :class="{ dim: weekFilterOn && !e.active_this_week, spanned: e.spanned }"
                :style="{ borderLeftColor: colorOf(e.course_name) }"
                :title="`${e.course_name} ${e.teacher || ''} ${e.weeks}周 ${e.start_time}-${e.end_time} ${e.location || ''}`"
              >
                <template v-if="!e.spanned">
                  <div class="tb-name">{{ e.course_name }}</div>
                  <div class="tb-meta mono">{{ e.teacher || '—' }} · {{ e.weeks }}周</div>
                  <div class="tb-meta mono">{{ e.location || '—' }}</div>
                </template>
              </div>
            </div>
          </template>
        </div>
      </section>

      <!-- 明细表 -->
      <section class="col-4 card">
        <header class="card-head">
          <div class="card-title">☷ 解析明细 <span class="en">ENTRIES</span></div>
        </header>
        <div class="en-head mono">
          <span style="flex:1.4">课程</span><span style="width:64px">教师</span>
          <span style="width:44px">星期</span><span style="width:88px">时间</span>
          <span style="width:76px">周次</span><span style="flex:1">教室</span>
        </div>
        <div class="en-scroll">
          <div v-if="!ps.entries.length" class="empty-note">暂无数据</div>
          <div v-for="e in ps.entries" :key="e.id" class="en-row" :class="{ dim: weekFilterOn && !e.active_this_week }">
            <span style="flex:1.4" :title="e.course_name">
              <i class="sw" :style="{ background: colorOf(e.course_name) }" />{{ e.course_name }}
            </span>
            <span style="width:64px">{{ e.teacher || '—' }}</span>
            <span style="width:44px" class="mono">{{ e.weekday_cn }}</span>
            <span style="width:88px" class="mono">{{ e.start_time }}-{{ e.end_time }}</span>
            <span style="width:76px" class="mono">{{ e.weeks }}周{{ e.week_type !== '全周' ? e.week_type : '' }}</span>
            <span style="flex:1" class="mono" :title="e.location">{{ e.room_no || e.location || '—' }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.pdf-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.pdf-head .sub { color: var(--text-3); font-size: 12px; }
.pdf-head .spacer { flex: 1; }

.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }

.drop-zone {
  border: 1.5px dashed rgba(107, 114, 128, 0.45); border-radius: 12px;
  padding: 26px 18px; text-align: center; cursor: pointer; transition: all .2s;
  background: rgba(107, 114, 128, 0.05);
}
.drop-zone:hover, .drop-zone.over { border-color: var(--accent, #4ade80); background: rgba(74, 222, 128, 0.06); }
.dz-ico { font-size: 26px; color: var(--accent, #4ade80); }
.dz-text { margin-top: 6px; color: #d1d5db; font-size: 14px; }
.dz-hint { margin-top: 4px; color: #6b7280; font-size: 11px; }

.up-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 4px; border-bottom: 1px solid rgba(42, 42, 42, 0.55); }
.up-row:last-child { border-bottom: none; }
.up-main { flex: 1; min-width: 0; }
.up-name { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 14px; color: #e5e7eb; }
.up-meta { margin-top: 3px; font-size: 11px; color: #6b7280; }

/* 失败原因：完整展示，不截断 */
.up-error {
  display: flex; align-items: flex-start; gap: 7px;
  margin-top: 7px; padding: 8px 10px; border-radius: 8px;
  background: rgba(248, 113, 113, 0.07);
  border: 1px solid rgba(248, 113, 113, 0.28);
}
.ue-ico { color: #f87171; font-size: 12px; line-height: 1.5; flex-shrink: 0; }
.ue-body { min-width: 0; }
.ue-title { font-size: 12px; color: #f87171; font-weight: 600; margin-bottom: 3px; }
.ue-text { font-size: 11.5px; color: var(--text-2, #9ca3af); line-height: 1.65; word-break: break-word; }

/* 处理建议 */
.up-sug-wrap { margin-top: 7px; }
.us-title { font-size: 10.5px; color: var(--text-3, #6b7280); margin-bottom: 3px; }
.up-sug { margin: 0 0 0 17px; padding: 0; font-size: 11.5px; color: var(--text-2, #9ca3af); line-height: 1.7; }
.up-sug li { margin: 2px 0; }

/* 失败项快捷补救 */
.up-ops { display: flex; gap: 7px; margin-top: 9px; flex-wrap: wrap; }

.filter-bar { display: flex; align-items: center; gap: 10px; padding: 12px 14px; flex-wrap: wrap; }
.f-item { width: 130px; }
.f-kw { width: 190px; }

.empty-note { padding: 26px 10px; text-align: center; color: #6b7280; font-size: 13px; }

.tt-grid { display: grid; gap: 4px; }
.tt-corner, .tt-day, .tt-sec { font-size: 11px; color: #9ca3af; text-align: center; padding: 4px 0; }
.tt-cell { min-height: 52px; border-radius: 6px; background: rgba(107, 114, 128, 0.06); padding: 2px; }
.tt-block {
  border-left: 3px solid #4ade80; border-radius: 4px; padding: 3px 5px; margin-bottom: 3px;
  background: rgba(30, 30, 30, 0.85); font-size: 11px; overflow: hidden;
}
.tt-block.spanned { opacity: 0; height: 6px; padding: 0; margin: 0; border: none; background: rgba(30, 30, 30, 0.85); }
.tt-block.dim { opacity: 0.28; border-left-style: dashed; }
.tb-name { color: #e5e7eb; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tb-meta { color: #6b7280; font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.en-head, .en-row { display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 6px 4px; }
.en-head { color: #6b7280; border-bottom: 1px solid rgba(42, 42, 42, 0.6); }
.en-row { border-bottom: 1px solid rgba(42, 42, 42, 0.35); color: #d1d5db; }
.en-row.dim { opacity: 0.35; }
.en-row > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.en-scroll { max-height: 560px; overflow-y: auto; }
.sw { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
</style>
