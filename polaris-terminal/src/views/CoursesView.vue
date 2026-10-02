<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NForm, NFormItem, NInput, NModal, NPopconfirm, NSelect, useMessage } from 'naive-ui'
import { store } from '../store'
import { coursesApi } from '../api'
import PdfScheduleView from './PdfScheduleView.vue'

const message = useMessage()
const route = useRoute()

/* ── 撤销错误课表：清空全部课程 ── */
const clearing = ref(false)
async function clearAll() {
  clearing.value = true
  try {
    const r = await store.clearCourses()
    message.success(`已清空 ${r.deleted} 门课程，可重新导入正确课表`)
    importResult.value = null
  } catch (err) {
    message.error('清空失败：' + err.message)
  } finally {
    clearing.value = false
  }
}

/* 删除单门课程（同名的多天安排属于同一课程，一并删除） */
async function removeCourse(s) {
  if (!s.id) { message.warning('无法定位该课程，请在课程清单中删除'); return }
  try {
    await store.removeCourse(s.id)
    message.success(`已删除「${s.name}」`)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── Excel 课表导入 ── */
const excelInput = ref(null)
const importing = ref(false)
const importResult = ref(null)

function pickExcel() { excelInput.value?.click() }
async function downloadTemplate() {
  try {
    await coursesApi.downloadImportTemplate()
    message.success('模板已下载，按表头填写后导入即可')
  } catch (err) {
    message.error('模板下载失败：' + err.message)
  }
}

/* 导入结果按教室统计 */
const importRoomStats = computed(() => {
  const items = importResult.value?.created_items || []
  const map = {}
  for (const c of items) {
    const rooms = c.rooms?.length ? c.rooms : ['未填教室']
    for (const r of rooms) map[r] = (map[r] || 0) + 1
  }
  return Object.entries(map).sort((a, b) => b[1] - a[1])
})
async function onExcelFile(e) {
  const f = e.target.files?.[0]
  if (!f) return
  if (!/\.xlsx?$/i.test(f.name)) {
    message.error('请选择 .xlsx / .xls 文件')
    e.target.value = ''
    return
  }
  importing.value = true
  importResult.value = null
  try {
    const result = await store.importCoursesExcel({ file: f })
    importResult.value = result
    if (result.created) {
      message.success(`导入成功 ${result.created} 门课${result.skipped ? `，跳过冲突 ${result.skipped} 门` : ''}`)
    } else {
      message.warning('未导入任何课程，请检查表格内容或与现有课程冲突')
    }
  } catch (err) {
    message.error('导入失败：' + err.message)
  } finally {
    importing.value = false
    e.target.value = ''
  }
}

const HOUR_START = 8
const HOUR_END = 21
const ROW_H = 56 // 每小时像素高度

const hours = Array.from({ length: HOUR_END - HOUR_START + 1 }, (_, i) => HOUR_START + i)
const tt = computed(() => store.weekTimetable)

const slotsByDay = computed(() => {
  const map = {}
  for (let d = 1; d <= 7; d++) map[d] = tt.value.slots.filter((s) => s.day === d)
  return map
})

function blockStyle(s) {
  const top = ((s.startMin ?? s.start * 60) - HOUR_START * 60) / 60 * ROW_H
  const height = ((s.endMin ?? s.end * 60) - (s.startMin ?? s.start * 60)) / 60 * ROW_H
  return {
    top: top + 2 + 'px',
    height: height - 6 + 'px',
    borderLeftColor: s.color,
    background: s.color + '1f',
  }
}

/* 冲突检测：同一天时间段相交 */
const conflicts = computed(() => {
  const list = []
  for (let d = 1; d <= 7; d++) {
    const arr = slotsByDay.value[d]
    for (let i = 0; i < arr.length; i++)
      for (let j = i + 1; j < arr.length; j++) {
        const a1 = arr[i].startMin ?? arr[i].start * 60, a2 = arr[i].endMin ?? arr[i].end * 60
        const b1 = arr[j].startMin ?? arr[j].start * 60, b2 = arr[j].endMin ?? arr[j].end * 60
        if (a1 < b2 && b1 < a2) {
          const fmt = (m) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
          list.push({ day: d, a: arr[i].name, b: arr[j].name, time: `${fmt(Math.max(a1, b1))}-${fmt(Math.min(a2, b2))}` })
        }
      }
  }
  return list
})

const stats = computed(() => {
  const total = tt.value.slots.length
  const minutes = tt.value.slots.reduce((s, x) => s + ((x.endMin ?? x.end * 60) - (x.startMin ?? x.start * 60)), 0)
  const hours = Math.round(minutes / 60 * 10) / 10
  const busiest = [...Array(7)].map((_, i) => tt.value.slots.filter((s) => s.day === i + 1).length)
  const maxDay = busiest.indexOf(Math.max(...busiest)) + 1
  return { total, hours, maxDay, freeSlots: (HOUR_END - HOUR_START) * 7 - Math.round(hours) }
})

const DAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

/* 按课程去重：一门课可能有多天安排，清单里只显示一条并带删除 */
const uniqueCourses = computed(() => {
  const map = new Map()
  for (const s of tt.value.slots) {
    const key = s.id ?? s.name
    if (!map.has(key)) map.set(key, s)
  }
  return [...map.values()]
})

/* ── 学期选择与管理 ── */
const selSemester = ref(null)
const showSemModal = ref(false)
const semesterOptions = computed(() => store.semesters.map((s) => ({ label: s.label + (s.isCurrent ? ' · 当前' : ''), value: s.value })))
const currentSemester = computed(() => store.semesterRaw.find((s) => s.is_current) || null)

async function switchSemester(id) {
  try {
    await store.loadSemesters(id)
    message.success(id ? `已切换到「${store.semesters.find((s) => s.value === id)?.label || id}」课表` : '已回到当前学期')
  } catch (err) {
    message.error('切换学期失败：' + err.message)
  }
}

const semEditing = ref(null)
const semForm = ref({ name: '', start_date: '', end_date: '', total_weeks: 20 })
const savingSem = ref(false)
function newSemester() {
  semEditing.value = null
  semForm.value = { name: '', start_date: '', end_date: '', total_weeks: 20 }
}
function editSemester(s) {
  semEditing.value = s
  semForm.value = { name: s.name, start_date: s.start_date || '', end_date: s.end_date || '', total_weeks: s.total_weeks }
}
async function saveSemester() {
  if (!semForm.value.name.trim()) { message.warning('学期名称必填'); return }
  savingSem.value = true
  try {
    const payload = {
      name: semForm.value.name.trim(),
      start_date: semForm.value.start_date || null,
      end_date: semForm.value.end_date || null,
      total_weeks: Number(semForm.value.total_weeks) || 20,
      is_current: semEditing.value ? semEditing.value.is_current : !store.semesters.length,
    }
    if (semEditing.value) await store.updateSemester(semEditing.value.id, payload)
    else await store.createSemester(payload)
    message.success('学期已保存')
    newSemester()
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingSem.value = false
  }
}
async function makeCurrent(s) {
  try {
    await store.setCurrentSemester(s.id)
    selSemester.value = null
    message.success(`「${s.name}」已设为当前学期`)
  } catch (err) {
    message.error('操作失败：' + err.message)
  }
}
async function removeSemester(s) {
  try {
    await store.removeSemester(s.id)
    message.success(`已删除「${s.name}」（其课程归属置空）`)
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 课程新增 / 编辑（含节次多段编辑 + 冲突预检）── */
const DAY_OPTS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((label, i) => ({ label, value: i + 1 }))
const WEEK_TYPE_OPTS = ['全周', '单周', '双周'].map((v) => ({ label: v, value: v }))
const TYPE_OPTS = ['必修', '选修', '实验', '实训', '讲座'].map((v) => ({ label: v, value: v }))
const COLOR_OPTS = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf', '#fb923c']
  .map((c) => ({ label: c, value: c }))

const showCourseModal = ref(false)
const courseEditing = ref(null)   // null = 新建
const savingCourse = ref(false)
const precheckResult = ref(null)  // { has_conflict, conflicts }
const cf = ref(blankCourse())

function blankCourse() {
  return {
    name: '', teacher: '', location: '', credit: 2, course_type: '必修',
    color: '#4ade80', semester_id: currentSemester.value?.id ?? null,
    schedules: [{ weekday: 1, start_time: '08:00', end_time: '09:40', weeks: '1-16', week_type: '全周', location: '' }],
  }
}
function openNewCourse() {
  courseEditing.value = null
  precheckResult.value = null
  cf.value = blankCourse()
  showCourseModal.value = true
}
async function openEditCourse(s) {
  try {
    await store.loadCourses()
    const full = store.coursesRaw.find((c) => c.id === s.id)
    if (!full) { message.warning('未找到该课程，请刷新后重试'); return }
    courseEditing.value = full
    precheckResult.value = null
    cf.value = {
      name: full.name, teacher: full.teacher || '', location: full.location || '',
      credit: full.credit ?? 0, course_type: full.course_type || '必修', color: full.color || '#4ade80',
      semester_id: full.semester_id ?? currentSemester.value?.id ?? null,
      schedules: (full.schedules || []).map((x) => ({
        weekday: x.weekday, start_time: x.start_time, end_time: x.end_time,
        weeks: x.weeks || '1-16', week_type: x.week_type || '全周', location: x.location || '',
      })),
    }
    if (!cf.value.schedules.length) cf.value.schedules.push({ weekday: 1, start_time: '08:00', end_time: '09:40', weeks: '1-16', week_type: '全周', location: '' })
    showCourseModal.value = true
  } catch (err) {
    message.error('加载课程失败：' + err.message)
  }
}
function addSection() {
  cf.value.schedules.push({ weekday: 1, start_time: '08:00', end_time: '09:40', weeks: '1-16', week_type: '全周', location: cf.value.location || '' })
}
function removeSection(i) {
  if (cf.value.schedules.length === 1) { message.warning('至少保留一段节次安排'); return }
  cf.value.schedules.splice(i, 1)
}

function buildCoursePayload() {
  const f = cf.value
  return {
    name: f.name.trim(), teacher: f.teacher.trim() || null, location: f.location.trim() || null,
    credit: Number(f.credit) || 0, course_type: f.course_type, color: f.color,
    semester_id: f.semester_id ?? null,
    schedules: f.schedules.map((s) => ({
      weekday: Number(s.weekday), start_time: s.start_time, end_time: s.end_time,
      weeks: s.weeks || '1-16', week_type: s.week_type || '全周',
      location: s.location?.trim() || f.location?.trim() || null,
    })),
  }
}
function validateForm(payload) {
  if (!payload.name) { message.warning('课程名称必填'); return false }
  for (const s of payload.schedules) {
    if (!/^\d{2}:\d{2}$/.test(s.start_time) || !/^\d{2}:\d{2}$/.test(s.end_time)) {
      message.warning('节次时间格式应为 HH:MM（如 08:00）'); return false
    }
    if (s.start_time >= s.end_time) { message.warning('结束时间必须晚于开始时间'); return false }
  }
  return true
}

async function runPrecheck() {
  const payload = buildCoursePayload()
  if (!validateForm(payload)) return
  try {
    precheckResult.value = await store.checkCourseConflicts(payload)
    if (!precheckResult.value.has_conflict) message.success('预检通过：与现有课表无冲突')
  } catch (err) {
    message.error('预检失败：' + err.message)
  }
}

async function saveCourse(force = false) {
  const payload = buildCoursePayload()
  if (!validateForm(payload)) return
  savingCourse.value = true
  try {
    await store.saveCourse(payload, { id: courseEditing.value?.id ?? null, force })
    message.success(force ? `已强制保存「${payload.name}」（忽略冲突）` : `已${courseEditing.value ? '更新' : '新增'}「${payload.name}」，课表与空教室预测已联动`)
    showCourseModal.value = false
  } catch (err) {
    const conflicts = err.detail?.detail?.conflicts || err.detail?.conflicts
    if (conflicts && conflicts.length) {
      precheckResult.value = { has_conflict: true, conflicts }
      message.warning('检测到时间冲突，可调整后保存或强制保存')
    } else {
      message.error('保存失败：' + err.message)
    }
  } finally {
    savingCourse.value = false
  }
}

/* 导入冲突明细（后端 import 返回 conflicts 数组） */
const importConflicts = computed(() => importResult.value?.conflicts || [])

/* ── 月历视图 ── */
const viewMode = ref('week')          // week | month
const calAnchor = ref(new Date())      // 当月 1 号
const calCourses = ref([])             // 该学期全部课程（含 schedules）
const calLoading = ref(false)
const selectedDay = ref(null)          // 'YYYY-MM-DD'

const calSemester = computed(() => {
  const id = selSemester.value
  if (id) return store.semesterRaw.find((s) => s.id === id) || null
  return currentSemester.value
})

function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 教学周：学期起始周一为第 1 周起点 */
function weekOfDate(d) {
  const sd = calSemester.value?.start_date
  if (!sd) return null
  const start = new Date(sd + 'T00:00:00')
  const monday = new Date(start)
  monday.setDate(start.getDate() - ((start.getDay() + 6) % 7))
  const diff = Math.floor((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - monday) / 86400000)
  const w = Math.floor(diff / 7) + 1
  const total = calSemester.value?.total_weeks || 20
  return w >= 1 && w <= total ? w : null
}

/** 周次表达式解析："1-16" / "1,3,5" / "2-15双" / "全周" */
function weekMatches(expr, weekType, week) {
  if (!week) return false
  let e = String(expr ?? '').trim()
  if (!e || e === '全周' || e === '每周') {
    if (/单/.test(e)) return week % 2 === 1
    if (/双/.test(e)) return week % 2 === 0
    return true
  }
  const odd = /单|^odd$/i.test(e) || weekType === '单周'
  const even = /双|^even$/i.test(e) || weekType === '双周'
  e = e.replace(/[单双每周odd\s]/gi, '')
  const set = new Set()
  for (const part of e.split(/[,，;；]/)) {
    if (!part) continue
    const m = part.match(/^(\d+)\s*[-~—]\s*(\d+)$/)
    if (m) { for (let i = +m[1]; i <= +m[2]; i++) set.add(i) }
    else if (/^\d+$/.test(part)) set.add(+part)
  }
  if (!set.has(week)) return false
  if (odd) return week % 2 === 1
  if (even) return week % 2 === 0
  return true
}

/** 月历网格：null 占位 + 每日 { d, date, week, classes[] } */
const calGrid = computed(() => {
  const a = calAnchor.value
  const year = a.getFullYear(), month = a.getMonth()
  const first = new Date(year, month, 1)
  const startPad = (first.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < startPad; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month, d)
    const dow = (date.getDay() + 6) % 7 + 1
    const week = weekOfDate(date)
    const classes = []
    if (week) {
      for (const c of calCourses.value) {
        for (const s of (c.schedules || [])) {
          if (s.weekday !== dow) continue
          if (!weekMatches(s.weeks, s.week_type, week)) continue
          classes.push({
            name: c.name, color: c.color || '#4ade80',
            room: s.location || c.location || '—',
            time: `${s.start_time}-${s.end_time}`, week,
          })
        }
      }
      classes.sort((x, y) => x.time.localeCompare(y.time))
    }
    cells.push({ d, key: ymd(date), date, week, classes })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  return { year, month: month + 1, cells }
})

const calTodayClasses = computed(() => {
  if (!selectedDay.value) return null
  return calGrid.value.cells.find((c) => c && c.key === selectedDay.value) || null
})

function shiftMonth(n) {
  const a = calAnchor.value
  calAnchor.value = new Date(a.getFullYear(), a.getMonth() + n, 1)
}

async function loadCalCourses() {
  calLoading.value = true
  try {
    const sid = selSemester.value ?? calSemester.value?.id ?? null
    calCourses.value = await store.loadCourses(sid ? { semester_id: sid } : {})
  } catch (err) {
    message.error('加载月历课程失败：' + err.message)
  } finally {
    calLoading.value = false
  }
}

function switchView(m) {
  viewMode.value = m
  if (m === 'month') loadCalCourses()
}

watch(selSemester, () => { if (viewMode.value === 'month') loadCalCourses() })

onMounted(() => {
  store.loadSemesters()
  if (route.query.view === 'month') switchView('month')
  else if (route.query.view === 'pdf') switchView('pdf')
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>课程表</h2>
      <span class="sub mono">SCHEDULE · 教学周 {{ tt.week || 1 }} · 第 {{ stats.total }} 门安排</span>
      <span class="spacer" />
      <template v-if="viewMode !== 'pdf'">
        <NSelect v-model:value="selSemester" size="small" class="sem-sel" placeholder="当前学期" clearable
                 :options="semesterOptions" @update:value="switchSemester" />
        <NButton size="small" quaternary @click="showSemModal = true; newSemester()">🗓 学期管理</NButton>
        <span class="chip" :class="conflicts.length ? 'chip-red' : 'chip-accent'">
          {{ conflicts.length ? `⚠ 检测到 ${conflicts.length} 处时间冲突` : '✓ 无时间冲突' }}
        </span>
      </template>
      <div class="view-seg">
        <button :class="{ on: viewMode === 'week' }" @click="switchView('week')">周视图</button>
        <button :class="{ on: viewMode === 'month' }" @click="switchView('month')">月历</button>
        <button :class="{ on: viewMode === 'pdf' }" @click="switchView('pdf')">PDF 课表</button>
      </div>
      <template v-if="viewMode !== 'pdf'">
        <input ref="excelInput" type="file" accept=".xlsx,.xls" style="display:none" @change="onExcelFile" />
        <NButton size="small" type="primary" @click="openNewCourse">＋ 新建课程</NButton>
        <NButton size="small" type="info" ghost :loading="importing" title="仅导入你本人的课程；全校教室课表请到「空教室」页导入" @click="pickExcel">⬆ 导入个人课表 Excel</NButton>
        <NButton size="small" quaternary @click="downloadTemplate">⬇ 导入模板</NButton>
        <NPopconfirm @positive-click="clearAll">
          <template #trigger>
            <NButton size="small" type="error" ghost :loading="clearing" :disabled="!stats.total">🗑 清空课表</NButton>
          </template>
          将删除全部 {{ stats.total }} 门课程（用于撤销错误导入），确定？
        </NPopconfirm>
      </template>
    </div>

    <!-- PDF 课表子模块 -->
    <PdfScheduleView v-if="viewMode === 'pdf'" />

    <template v-else>
    <!-- 导入结果提示（含冲突明细） -->
    <div v-if="importResult" class="imp-bar">
      <span class="chip chip-accent">✓ 导入 {{ importResult.created || 0 }} 门</span>
      <span v-if="importResult.skipped" class="chip chip-red">跳过 {{ importResult.skipped }} 门（时间冲突）</span>
      <span v-if="importRoomStats.length" class="imp-rooms">
        涉及教室：<span v-for="[room, n] in importRoomStats.slice(0, 6)" :key="room" class="room-tag mono">{{ room }}×{{ n }}</span>
        <span v-if="importRoomStats.length > 6" class="c3 mono" style="font-size:11px">等 {{ importRoomStats.length }} 间</span>
      </span>
      <span class="c3" style="font-size:11px">课表已同步到「空教室」模块：上课时段将自动排除对应教室</span>
      <span class="spacer" />
      <NButton size="tiny" quaternary @click="importResult = null">关闭</NButton>
    </div>
    <div v-if="importConflicts.length" class="imp-detail">
      <div class="imd-title mono">⚠ 导入冲突明细（{{ importConflicts.length }} 门被跳过）</div>
      <div v-for="(c, i) in importConflicts" :key="i" class="imd-row">
        <span class="chip chip-red">{{ c.name }}</span>
        <span v-for="(x, j) in c.conflicts" :key="j" class="mono c3" style="font-size:11px">
          周{{ '一二三四五六日'[x.weekday - 1] }} {{ x.start_time }}-{{ x.end_time }} ↔ {{ x.course_b }}
        </span>
      </div>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big">{{ stats.total }}</div>
        <div class="label-3">本周课程安排</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ stats.hours }}h</div>
        <div class="label-3">总课时时长</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#facc15; text-shadow:0 0 14px #facc1566">{{ DAY_CN[stats.maxDay - 1] }}</div>
        <div class="label-3">最忙的一天</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#c084fc; text-shadow:0 0 14px #c084fc66">{{ stats.freeSlots }}h</div>
        <div class="label-3">可支配空闲</div>
      </div>
    </div>

    <section v-if="viewMode === 'week'" class="card">
      <header class="card-head">
        <div class="card-title">▤ 周课表 <span class="en">WEEKLY GRID</span></div>
        <div class="legend">
          <span class="lg"><i class="dot dot-green" />进行中/自习</span>
          <span class="lg"><i class="dot dot-blue" />专业必修</span>
          <span class="lg"><i class="dot dot-yellow" />公共/强化</span>
          <span class="lg"><i class="dot dot-red" />实验/冲突关注</span>
        </div>
      </header>

      <div class="tt-wrap">
        <div class="tt-head">
          <div class="corner mono">时间</div>
          <div v-for="(d, i) in DAY_CN" :key="d" class="day-head" :class="{ today: i === 2 }">
            {{ d }}
            <span v-if="i === 2" class="today-tag mono">TODAY</span>
          </div>
        </div>

        <div class="tt-body">
          <div class="hours">
            <div v-for="h in hours" :key="h" class="hour-cell mono" :style="{ height: ROW_H + 'px' }">{{ h }}:00</div>
          </div>
          <div v-for="d in 7" :key="d" class="day-col" :style="{ height: (HOUR_END - HOUR_START) * ROW_H + 'px' }">
            <div v-for="h in hours" :key="h" class="grid-line" :style="{ height: ROW_H + 'px' }" />
            <div
              v-for="s in slotsByDay[d]"
              :key="s.name"
              class="slot"
              :style="blockStyle(s)"
              :title="`${s.name} · ${s.room} · ${s.weeks}`"
            >
              <div class="s-name">{{ s.name }}</div>
              <div class="s-room mono">{{ s.room }}</div>
              <div class="s-weeks mono">{{ s.weeks }} · {{ s.startHm || s.start + ':00' }}-{{ s.endHm || s.end + ':00' }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 月历视图 -->
    <section v-else class="card cal-card">
      <header class="card-head">
        <div class="card-title">🗓 课程月历 <span class="en">MONTHLY</span></div>
        <div class="cal-nav">
          <button class="cal-btn" @click="shiftMonth(-1)">‹</button>
          <span class="mono cal-label">{{ calGrid.year }} 年 {{ calGrid.month }} 月</span>
          <button class="cal-btn" @click="shiftMonth(1)">›</button>
          <button class="cal-btn today" @click="calAnchor = new Date()">今天</button>
        </div>
      </header>
      <div v-if="!calSemester || !calSemester.start_date" class="empty">
        当前学期缺少开始日期，无法推算教学周。请先在「学期管理」中设置起止日期。
      </div>
      <template v-else>
        <div class="cal-weekhead">
          <span v-for="w in DAY_CN" :key="w">{{ w }}</span>
        </div>
        <div class="cal-month-grid">
          <div v-for="(c, i) in calGrid.cells" :key="i"
               class="cal-cell" :class="{ blank: !c, 'has-cls': c && c.classes.length, sel: c && c.key === selectedDay }"
               @click="c && (selectedDay = c.key)">
            <template v-if="c">
              <div class="cc-top">
                <span class="cc-day mono" :class="{ istoday: c.key === ymd(new Date()) }">{{ c.d }}</span>
                <span v-if="c.week" class="cc-week mono">W{{ c.week }}</span>
              </div>
              <div class="cc-chips">
                <span v-for="(x, j) in c.classes.slice(0, 3)" :key="j" class="cc-chip" :style="{ borderLeftColor: x.color }">
                  {{ x.name }}
                </span>
                <span v-if="c.classes.length > 3" class="cc-more mono">+{{ c.classes.length - 3 }}</span>
              </div>
            </template>
          </div>
        </div>
        <!-- 选中日详情 -->
        <div v-if="calTodayClasses" class="cal-day-detail">
          <div class="cdd-head">
            <span class="mono">{{ calTodayClasses.key }}</span>
            <span class="cdd-week">{{ DAY_CN[(calTodayClasses.date.getDay() + 6) % 7] }}
              <em v-if="calTodayClasses.week">· 教学周第 {{ calTodayClasses.week }} 周</em>
              <em v-else>· 非教学周</em>
            </span>
            <span class="spacer" />
            <NButton size="tiny" quaternary @click="selectedDay = null">关闭</NButton>
          </div>
          <div v-if="calTodayClasses.classes.length" class="cdd-list">
            <div v-for="(x, i) in calTodayClasses.classes" :key="i" class="cdd-row" :style="{ borderLeftColor: x.color }">
              <span class="mono cdd-time">{{ x.time }}</span>
              <span class="cdd-name">{{ x.name }}</span>
              <span class="cdd-room mono">{{ x.room }}</span>
            </div>
          </div>
          <div v-else class="cdd-empty">当日无课程安排 ✦</div>
        </div>
      </template>
    </section>

    <div class="grid" style="margin-top: 16px">
      <section class="col-7 card">
        <header class="card-head"><div class="card-title">⚠ 冲突检测 <span class="en">CONFLICT CHECK</span></div></header>
        <div v-if="conflicts.length">
          <div v-for="(c, i) in conflicts" :key="i" class="row-line">
            <span class="dot dot-red" />
            <span class="mono" style="font-size:12px">周{{ '一二三四五六日'[c.day - 1] }} {{ c.time }}</span>
            <span style="font-size:12.5px">{{ c.a }} ↔ {{ c.b }}</span>
            <span class="spacer" />
            <span class="chip chip-red">时间重叠</span>
          </div>
        </div>
        <div v-else class="empty">当前课表无时间冲突 ✦</div>
      </section>

      <section class="col-5 card">
        <header class="card-head">
          <div class="card-title">≡ 课程清单 <span class="en">COURSE LIST</span></div>
          <span class="c3" style="font-size:10px">点 ✎ 编辑 · ✕ 删除</span>
        </header>
        <div class="course-chips">
          <span v-for="s in uniqueCourses" :key="s.id || s.name" class="c-chip" :style="{ borderColor: s.color + '55', color: s.color }">
            {{ s.name }}
            <em class="mono">{{ s.room }}</em>
            <button class="x" title="编辑该课程" @click="openEditCourse(s)">✎</button>
            <button class="x" title="删除该课程" @click="removeCourse(s)">✕</button>
          </span>
        </div>
      </section>
    </div>
    </template>

    <!-- 课程新增/编辑弹窗 -->
    <NModal v-model:show="showCourseModal" preset="card" :title="courseEditing ? `✎ 编辑课程 · ${courseEditing.name}` : '＋ 新建课程'"
           style="width: 640px" :bordered="false">
      <NForm label-placement="left" label-width="72" size="small">
        <div class="cf-grid">
          <NFormItem label="课程名称" required><NInput v-model:value="cf.name" placeholder="如 高等数学" /></NFormItem>
          <NFormItem label="授课教师"><NInput v-model:value="cf.teacher" placeholder="选填" /></NFormItem>
          <NFormItem label="上课地点"><NInput v-model:value="cf.location" placeholder="如 信东201（节次可分别指定）" /></NFormItem>
          <NFormItem label="学分"><NInput v-model:value="cf.credit" type="number" placeholder="2" /></NFormItem>
          <NFormItem label="课程类型"><NSelect v-model:value="cf.course_type" :options="TYPE_OPTS" /></NFormItem>
          <NFormItem label="配色">
            <div class="color-row">
              <button v-for="c in COLOR_OPTS" :key="c" class="c-dot" :class="{ on: cf.color === c }"
                      :style="{ background: c }" :title="c" @click="cf.color = c" />
            </div>
          </NFormItem>
          <NFormItem label="所属学期">
            <NSelect v-model:value="cf.semester_id" :options="semesterOptions" clearable placeholder="默认当前学期" />
          </NFormItem>
        </div>

        <div class="sec-head">
          <span class="sec-title">节次安排（{{ cf.schedules.length }} 段）</span>
          <NButton size="tiny" tertiary type="primary" @click="addSection">＋ 添加一段</NButton>
        </div>
        <div v-for="(s, i) in cf.schedules" :key="i" class="sec-row">
          <NSelect v-model:value="s.weekday" size="tiny" class="sec-day" :options="DAY_OPTS" />
          <NInput v-model:value="s.start_time" size="tiny" class="sec-time" placeholder="08:00" />
          <span class="c3">—</span>
          <NInput v-model:value="s.end_time" size="tiny" class="sec-time" placeholder="09:40" />
          <NInput v-model:value="s.weeks" size="tiny" class="sec-weeks" placeholder="1-16" />
          <NSelect v-model:value="s.week_type" size="tiny" class="sec-wt" :options="WEEK_TYPE_OPTS" />
          <NInput v-model:value="s.location" size="tiny" class="sec-loc" placeholder="教室（默认同上课地点）" />
          <button class="sec-del" title="删除该段" @click="removeSection(i)">✕</button>
        </div>

        <div v-if="precheckResult" class="pre-box" :class="precheckResult.has_conflict ? 'bad' : 'good'">
          <div class="mono" style="font-size:11.5px">
            {{ precheckResult.has_conflict ? `⚠ 预检发现 ${precheckResult.conflicts.length} 处冲突` : '✓ 预检通过，无冲突' }}
          </div>
          <div v-for="(x, i) in precheckResult.conflicts" :key="i" class="pre-row mono">
            周{{ '一二三四五六日'[x.weekday - 1] }} {{ x.start_time }}-{{ x.end_time }} · {{ x.weeks }}周 ·
            {{ x.course_a }} ↔ {{ x.course_b }}<span v-if="x.location_b"> @{{ x.location_b }}</span>
          </div>
        </div>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" quaternary :loading="savingCourse" @click="runPrecheck">⚡ 冲突预检</NButton>
          <NButton size="small" @click="showCourseModal = false">取消</NButton>
          <NButton v-if="precheckResult?.has_conflict" size="small" type="warning" :loading="savingCourse" @click="saveCourse(true)">强制保存</NButton>
          <NButton size="small" type="primary" :loading="savingCourse" @click="saveCourse(false)">保存</NButton>
        </div>
      </template>
    </NModal>

    <!-- 学期管理弹窗 -->
    <NModal v-model:show="showSemModal" preset="card" title="🗓 学期管理" style="width: 720px" :bordered="false">
      <div class="sem-list">
        <div v-for="s in store.semesterRaw" :key="s.id" class="sem-row" :class="{ cur: s.is_current }">
          <div class="sem-mid">
            <div class="sem-name">{{ s.name }}<span v-if="s.is_current" class="chip chip-accent" style="margin-left:8px">当前</span></div>
            <div class="sem-meta mono">{{ s.start_date || '—' }} ~ {{ s.end_date || '—' }} · {{ s.total_weeks }} 周 · 第 {{ s.current_week ?? '—' }} 周</div>
          </div>
          <NButton size="tiny" quaternary :disabled="s.is_current" @click="makeCurrent(s)">设为当前</NButton>
          <NButton size="tiny" quaternary @click="editSemester(s)">编辑</NButton>
          <NPopconfirm @positive-click="removeSemester(s)">
            <template #trigger><NButton size="tiny" quaternary type="error">删除</NButton></template>
            删除「{{ s.name }}」？其下课程归属将置空，课程本身保留。
          </NPopconfirm>
        </div>
      </div>
      <div class="sem-form">
        <div class="sf-title mono">{{ semEditing ? `✎ 编辑「${semEditing.name}」` : '＋ 新建学期' }}</div>
        <NForm label-placement="left" label-width="72" size="small">
          <div class="sf-grid">
            <NFormItem label="名称" required><NInput v-model:value="semForm.name" placeholder="如 2026-2027 学年第一学期" /></NFormItem>
            <NFormItem label="总周数"><NInput v-model:value="semForm.total_weeks" type="number" /></NFormItem>
            <NFormItem label="开始日期"><NInput v-model:value="semForm.start_date" type="date" /></NFormItem>
            <NFormItem label="结束日期"><NInput v-model:value="semForm.end_date" type="date" /></NFormItem>
          </div>
        </NForm>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <NButton v-if="semEditing" size="small" quaternary @click="newSemester">取消编辑</NButton>
          <NButton size="small" type="primary" :loading="savingSem" @click="saveSemester">{{ semEditing ? '保存修改' : '创建学期' }}</NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px 16px; min-width: 0;
}
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.legend { display: flex; gap: 12px; }
.lg { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-3); }
.empty { color: var(--text-3); font-size: 12px; padding: 16px 0; text-align: center; }

.tt-wrap { overflow-x: auto; }
.tt-head { display: grid; grid-template-columns: 56px repeat(7, minmax(104px, 1fr)); border-bottom: 1px solid var(--border); }
.corner { font-size: 10px; color: var(--text-3); padding: 6px 4px; }
.day-head {
  position: relative; text-align: center; font-size: 12px; color: var(--text-2);
  padding: 8px 0 10px; border-left: 1px solid var(--border);
}
.day-head.today { color: var(--accent); background: rgba(74, 222, 128, 0.05); }
.today-tag { position: absolute; right: 6px; top: 6px; font-size: 8px; color: var(--accent); letter-spacing: 1px; }

.tt-body { display: grid; grid-template-columns: 56px repeat(7, minmax(104px, 1fr)); }
.hours { display: flex; flex-direction: column; }
.hour-cell { font-size: 10px; color: var(--text-3); padding-top: 2px; text-align: right; padding-right: 8px; }
.day-col { position: relative; border-left: 1px solid var(--border); }
.grid-line { border-bottom: 1px dashed rgba(42, 42, 42, 0.75); }
.slot {
  position: absolute; left: 3px; right: 3px;
  border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 6px 8px; overflow: hidden;
  backdrop-filter: blur(2px);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.slot:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45); }
.s-name { font-size: 12px; color: var(--text-1); line-height: 1.3; }
.s-room { font-size: 10px; color: var(--text-2); margin-top: 2px; }
.s-weeks { font-size: 9px; color: var(--text-3); margin-top: 2px; }

.imp-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; padding: 8px 14px; border-radius: 10px; background: rgba(74, 222, 128, 0.06); border: 1px solid rgba(74, 222, 128, 0.25); flex-wrap: wrap; }
.imp-rooms { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-3); flex-wrap: wrap; }
.room-tag { font-size: 10.5px; padding: 1px 7px; border-radius: 999px; border: 1px solid rgba(96, 165, 250, 0.4); color: #60a5fa; background: rgba(96, 165, 250, 0.08); }
.c3 { color: var(--text-3); }
.course-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.c-chip {
  font-size: 11.5px; padding: 4px 10px; border: 1px solid; border-radius: 999px;
  display: inline-flex; align-items: center; gap: 6px; background: rgba(255, 255, 255, 0.02);
}
.c-chip em { font-style: normal; font-size: 10px; color: var(--text-3); }
.c-chip .x {
  all: unset; cursor: pointer; font-size: 10px; line-height: 1; padding: 1px 3px; border-radius: 4px;
  color: var(--text-3);
}
.c-chip .x:hover { color: #f87171; background: rgba(248, 113, 113, 0.12); }
.spacer { flex: 1; }

.sem-sel { width: 190px; }

/* 导入冲突明细 */
.imp-detail { margin: -6px 0 14px; padding: 10px 14px; border-radius: 10px; background: rgba(248,113,113,0.05); border: 1px solid rgba(248,113,113,0.25); }
.imd-title { font-size: 11px; color: #f87171; margin-bottom: 8px; }
.imd-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 3px 0; }

/* 课程表单 */
.cf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.color-row { display: flex; gap: 6px; }
.c-dot { width: 18px; height: 18px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; }
.c-dot.on { border-color: #fff; box-shadow: 0 0 8px rgba(255,255,255,0.4); }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin: 8px 0 6px; }
.sec-title { font-size: 11px; color: var(--text-3); }
.sec-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.sec-day { width: 76px; }
.sec-time { width: 72px; }
.sec-weeks { width: 90px; }
.sec-wt { width: 76px; }
.sec-loc { flex: 1; min-width: 120px; }
.sec-del { all: unset; cursor: pointer; color: var(--text-3); font-size: 11px; padding: 2px 5px; border-radius: 4px; }
.sec-del:hover { color: #f87171; background: rgba(248,113,113,0.12); }
.pre-box { margin-top: 10px; padding: 9px 12px; border-radius: 10px; font-size: 12px; }
.pre-box.good { background: rgba(74,222,128,0.06); border: 1px solid rgba(74,222,128,0.3); color: var(--accent); }
.pre-box.bad { background: rgba(248,113,113,0.06); border: 1px solid rgba(248,113,113,0.3); color: #f87171; }
.pre-row { margin-top: 4px; font-size: 11px; color: var(--text-2); }

/* 学期管理 */
.sem-list { max-height: 260px; overflow-y: auto; margin-bottom: 14px; }
.sem-row { display: flex; align-items: center; gap: 8px; padding: 8px 4px; border-bottom: 1px dashed var(--border); }
.sem-row:last-child { border-bottom: none; }
.sem-row.cur { background: rgba(74,222,128,0.04); border-radius: 8px; }
.sem-mid { flex: 1; min-width: 0; }
.sem-name { font-size: 13px; color: var(--text-1); }
.sem-meta { font-size: 10.5px; color: var(--text-3); margin-top: 2px; }
.sem-form { border-top: 1px solid var(--border); padding-top: 12px; }
.sf-title { font-size: 11.5px; color: var(--text-2); margin-bottom: 8px; }
.sf-grid { display: grid; grid-template-columns: 1.4fr 0.6fr 1fr 1fr; gap: 0 12px; }

/* 视图切换 */
.view-seg { display: inline-flex; border: 1px solid var(--border); border-radius: 9px; overflow: hidden; }
.view-seg button {
  all: unset; cursor: pointer; padding: 4px 12px; font-size: 12px; color: var(--text-3);
}
.view-seg button.on { background: rgba(74, 222, 128, 0.14); color: var(--accent); }

/* 月历 */
.cal-nav { display: flex; align-items: center; gap: 8px; }
.cal-label { font-size: 13px; color: var(--text-1); min-width: 110px; text-align: center; }
.cal-btn {
  all: unset; cursor: pointer; width: 26px; height: 24px; display: grid; place-items: center;
  border: 1px solid var(--border); border-radius: 8px; color: var(--text-2); font-size: 14px;
}
.cal-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.cal-btn.today { width: auto; padding: 0 10px; font-size: 11px; }
.cal-weekhead { display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 6px; }
.cal-weekhead span { text-align: center; font-size: 11px; color: var(--text-3); }
.cal-month-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.cal-cell {
  min-height: 86px; border: 1px solid var(--border); border-radius: 10px; padding: 6px 7px;
  background: rgba(255, 255, 255, 0.015); cursor: pointer; overflow: hidden;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.cal-cell:hover { border-color: rgba(74, 222, 128, 0.45); }
.cal-cell.blank { border: none; background: transparent; cursor: default; }
.cal-cell.sel { border-color: var(--accent); background: rgba(74, 222, 128, 0.06); }
.cc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.cc-day { font-size: 12px; color: var(--text-2); }
.cc-day.istoday {
  background: var(--accent); color: #06170d; font-weight: 700;
  border-radius: 50%; width: 20px; height: 20px; display: grid; place-items: center;
}
.cc-week { font-size: 9px; color: var(--text-3); }
.cc-chips { display: flex; flex-direction: column; gap: 2px; }
.cc-chip {
  font-size: 10px; color: var(--text-2); border-left: 3px solid; padding: 1px 5px;
  border-radius: 4px; background: rgba(255, 255, 255, 0.03);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cc-more { font-size: 9px; color: var(--text-3); padding-left: 5px; }
.cal-day-detail { margin-top: 12px; border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; background: rgba(74, 222, 128, 0.03); }
.cdd-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 12px; color: var(--text-2); }
.cdd-week em { font-style: normal; color: var(--text-3); font-size: 11px; }
.cdd-list { display: flex; flex-direction: column; gap: 5px; }
.cdd-row { display: flex; align-items: center; gap: 12px; border-left: 3px solid; padding: 4px 10px; border-radius: 6px; background: rgba(255, 255, 255, 0.02); }
.cdd-time { font-size: 11px; color: var(--text-3); min-width: 96px; }
.cdd-name { font-size: 12.5px; color: var(--text-1); flex: 1; }
.cdd-room { font-size: 11px; color: var(--text-2); }
.cdd-empty { font-size: 12px; color: var(--text-3); padding: 6px 0; }
</style>
