<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NPopconfirm, NRadio, NRadioGroup, NSelect, NSwitch, useMessage } from 'naive-ui'
import { classroomApi } from '../api'
import { store } from '../store'
import GlowChart from '../components/GlowChart.vue'
import { axisBase, glowBar } from '../utils/chart'

const message = useMessage()
const picked = ref(null)
watch(() => store.classroom.predict, (p) => { if (!picked.value && p.length) picked.value = p[0].room }, { immediate: true })

/* ── 采集记录：照片预览 + 删除 ── */
const previewRec = ref(null)
function openPreview(r) { if (r.photoUrl) previewRec.value = r }
async function removeRecord(r) {
  if (!r.id) { message.warning('该记录缺少 ID，无法删除'); return }
  try {
    await store.removeClassroomStatus(r.id)
    message.success('已删除该采集记录')
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 采集记录：按楼/教室筛选 + 服务端分页 ── */
const REC_PAGE_SIZE = 8
const recBuilding = ref(null)
const recRoom = ref(null)
const recPage = ref(1)
const recData = ref({ total: 0, items: [] })
const recLoading = ref(false)
const recRoomOptions = computed(() => {
  const b = (store.classroom.overview || []).find((x) => x.building === recBuilding.value)
  return (b?.rooms || []).map((r) => ({ label: r, value: r }))
})
const recTotalPages = computed(() => Math.max(1, Math.ceil(recData.value.total / REC_PAGE_SIZE)))

function mapLog(r) {
  return {
    id: r.id,
    time: (r.recorded_at || '').slice(5, 16),
    room: r.name,
    state: r.status_label,
    source: { miniapp: '小程序拍照', manual: '手动标记', ai_vision: 'AI 识图', web: 'Web 上报', ai: 'AI 助手' }[r.source] || r.source,
    note: r.note || '',
    photo: !!r.photo_url,
    photoUrl: r.photo_url || null,
  }
}

async function loadRecords() {
  recLoading.value = true
  try {
    const d = await classroomApi.recent(REC_PAGE_SIZE, {
      building: recBuilding.value || undefined,
      room_no: recRoom.value || undefined,
      offset: (recPage.value - 1) * REC_PAGE_SIZE,
    })
    recData.value = { total: d?.total || 0, items: (d?.items || []).map(mapLog) }
    // 删除后当前页可能越界，回退到最后一页
    const pages = Math.max(1, Math.ceil((d?.total || 0) / REC_PAGE_SIZE))
    if (recPage.value > pages) {
      recPage.value = pages
      const d2 = await classroomApi.recent(REC_PAGE_SIZE, {
        building: recBuilding.value || undefined,
        room_no: recRoom.value || undefined,
        offset: (pages - 1) * REC_PAGE_SIZE,
      })
      recData.value = { total: d2?.total || 0, items: (d2?.items || []).map(mapLog) }
    }
  } catch (err) {
    message.error('加载采集记录失败：' + err.message)
  } finally {
    recLoading.value = false
  }
}

function gotoRecPage(p) {
  const np = Math.min(Math.max(1, p), recTotalPages.value)
  if (np === recPage.value) return
  recPage.value = np
  loadRecords()
}

watch([recBuilding], () => { recRoom.value = null; recPage.value = 1; loadRecords() })
watch([recRoom], () => { recPage.value = 1; loadRecords() })
// store 刷新（上报/删除/导入后）联动重拉当前页
watch(() => store.classroom.records, () => { void loadRecords() }, { deep: false })

/* ── 教室课表 Excel 导入（全校占用数据，与个人课表完全分离）── */
const excelInput = ref(null)
const importing = ref(false)
const clearingSchedule = ref(false)
// 用 computed 引用 store，避免 setup 快照导致刷新后视图不更新
const schedList = computed(() => store.classroom.schedule || { total: 0, items: [] })
function pickExcel() { excelInput.value?.click() }
async function loadScheduleList() {
  try { await store.loadClassroomSchedule() } catch { /* 静默 */ }
}
async function onExcelFile(e) {
  const fs = [...(e.target.files || [])].filter((f) => /\.xlsx?$/i.test(f.name) && !f.name.startsWith('~$'))
  e.target.value = ''
  if (!fs.length) return
  importing.value = true
  try {
    const r = await store.importClassroomSchedule(fs)
    if (r.created) {
      const rooms = (r.rooms || []).join('、')
      message.success(`教室课表导入 ${r.created} 门课${r.cleared ? `，已替换旧数据 ${r.cleared} 门` : ''}${rooms ? `，覆盖教室：${rooms}` : ''}，热力图已联动更新`)
    } else {
      message.warning('未解析到有效课程行，请检查表格内容')
    }
    if (r.file_errors?.length) message.warning(`部分文件跳过：${r.file_errors.join('；')}`, { duration: 6000 })
    await loadScheduleList()
    await loadCampus()
  } catch (err) {
    message.error('导入失败：' + err.message)
  } finally {
    importing.value = false
  }
}
async function clearSchedule() {
  clearingSchedule.value = true
  try {
    const r = await store.clearClassroomSchedule()
    message.success(`已清空教室课表（${r.deleted} 门），个人课表不受影响`)
    await loadScheduleList()
    await loadCampus()
  } catch (err) {
    message.error('清空失败：' + err.message)
  } finally {
    clearingSchedule.value = false
  }
}

/* ── 教室课表 Excel 解析检查（批量，不落库；可导出 xlsx/json）── */
const parseInput = ref(null)
const showParse = ref(false)
const parsing = ref(false)
const parseResult = ref(null)
const parseFiles = ref([])   // 保留原始 File 供导出
const parseTab = ref('overview')
function pickParseFiles() { parseInput.value?.click() }
async function onParseFiles(e) {
  const fs = [...(e.target.files || [])].filter((f) => /\.xlsx?$/i.test(f.name) && !f.name.startsWith('~$'))
  e.target.value = ''
  if (!fs.length) { message.warning('请选择 .xlsx 文件（Excel 临时锁文件已自动忽略）'); return }
  parseFiles.value = fs
  parsing.value = true
  parseTab.value = 'overview'
  try {
    parseResult.value = await classroomApi.parseScheduleExcel(fs)
    showParse.value = true
    const s = parseResult.value.summary
    message.success(`解析完成：${s.file_count} 个文件 / ${s.total_entries} 条课程，${s.total_errors} 个异常`)
  } catch (err) {
    message.error('解析失败：' + err.message)
  } finally {
    parsing.value = false
  }
}
async function exportParse(fmt) {
  if (!parseFiles.value.length) return
  try {
    await classroomApi.exportScheduleParse(parseFiles.value, fmt)
    message.success(`已导出 ${fmt.toUpperCase()}`)
  } catch (err) {
    message.error('导出失败：' + err.message)
  }
}
// 明细表：把每个文件的 entries 摊平
const parseRows = computed(() => {
  const out = []
  for (const f of parseResult.value?.files || [])
    for (const e of f.entries) out.push(e)
  return out
})

/* ── 教室使用信息 Excel 导入（防重复录入）── */
const usageInput = ref(null)
const usageImporting = ref(false)
function pickUsageExcel() { usageInput.value?.click() }
async function onUsageExcelFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  if (!/\.xlsx?$/i.test(f.name)) { message.error('请选择 .xlsx / .xls 文件'); return }
  usageImporting.value = true
  try {
    const r = await store.importClassroomUsageExcel(f)
    const bad = (r.skipped_items || []).length + (r.error_items || []).length
    if (r.created && !bad) message.success(`导入 ${r.created} 条使用记录，热力图已联动更新`)
    else if (r.created) message.warning(`导入 ${r.created} 条；${bad} 条被拦截（重复录入或格式错误），详见提示`)
    else message.error('未导入任何记录：' + ((r.skipped_items || [])[0]?.reason || (r.error_items || [])[0]?.reason || '请检查表格内容'))
    await loadCampus()
  } catch (err) {
    message.error('导入失败：' + err.message)
  } finally {
    usageImporting.value = false
  }
}
function downloadUsageTemplate() {
  classroomApi.downloadUsageTemplate().catch((err) => message.error('模板下载失败：' + err.message))
}

/* ── 教室管理（信息 CRUD）── */
const showManage = ref(false)
const manageLoading = ref(false)
const manageBuilding = ref(null)
const manageKeyword = ref('')
const rooms = computed(() => store.classroomRooms)
const roomTypeOptions = ['普通教室', '多媒体教室', '机房', '实验室', '语音室', '会议室'].map((v) => ({ label: v, value: v }))

async function reloadRooms() {
  manageLoading.value = true
  try {
    await store.loadClassrooms({
      building: manageBuilding.value || undefined,
      keyword: manageKeyword.value.trim() || undefined,
    })
  } catch (err) {
    message.error('加载教室列表失败：' + err.message)
  } finally {
    manageLoading.value = false
  }
}
async function openManage() {
  showManage.value = true
  if (!rooms.value.length) await reloadRooms()
}

const showRoomForm = ref(false)
const roomEditing = ref(null)   // null = 新建
const savingRoom = ref(false)
const roomForm = ref({})
function blankRoom() {
  return {
    building: manageBuilding.value || '', room_no: '', floor: null,
    capacity: 60, seats: 0, open_time: '07:00', close_time: '22:30',
    room_type: '普通教室', has_projector: true, has_ac: true, note: '',
  }
}
function newRoom() {
  roomEditing.value = null
  roomForm.value = blankRoom()
  showRoomForm.value = true
}
function editRoom(r) {
  roomEditing.value = r
  roomForm.value = { ...r, note: r.note || '' }
  showRoomForm.value = true
}
async function saveRoom() {
  const f = roomForm.value
  if (!f.building?.trim() || !f.room_no?.trim()) { message.warning('教学楼与教室编号必填'); return }
  const payload = {
    building: f.building.trim(), room_no: f.room_no.trim(),
    floor: f.floor === '' || f.floor == null ? null : Number(f.floor),
    capacity: Number(f.capacity) || 0, seats: Number(f.seats) || 0,
    open_time: f.open_time || '07:00', close_time: f.close_time || '22:30',
    room_type: f.room_type || '普通教室',
    has_projector: !!f.has_projector, has_ac: !!f.has_ac,
    note: f.note || null,
  }
  savingRoom.value = true
  try {
    if (roomEditing.value) {
      await store.updateClassroom(roomEditing.value.id, payload)
      message.success(`已更新 ${payload.building} ${payload.room_no}`)
    } else {
      await store.createClassroom(payload)
      message.success(`已新增教室 ${payload.building} ${payload.room_no}`)
    }
    showRoomForm.value = false
    await reloadRooms()
    await loadCampus()
  } catch (err) {
    message.error('保存失败：' + err.message)
  } finally {
    savingRoom.value = false
  }
}
async function toggleRoomActive(r) {
  try {
    await store.updateClassroom(r.id, { is_active: !r.is_active })
    message.success(`${r.room_no} 已${r.is_active ? '停用' : '启用'}`)
    await reloadRooms()
    await loadCampus()
  } catch (err) {
    message.error('操作失败：' + err.message)
  }
}
async function removeRoom(r) {
  try {
    await store.removeClassroom(r.id, true)
    message.success(`已删除 ${r.building} ${r.room_no}`)
    await reloadRooms()
    await loadCampus()
  } catch (err) {
    message.error('删除失败：' + err.message)
  }
}

/* ── 照片上报 / AI 识图 ── */
const showUpload = ref(false)
const fileInput = ref(null)
const photoFile = ref(null)
const photoPreview = ref('')
const uploading = ref(false)
const recognizing = ref(false)
const form = ref({ building: '', room_no: '', status: 'free', note: '' })
const aiResult = ref(null)

const buildingOptions = computed(() =>
  (store.classroom.overview || []).map((b) => ({ label: b.building, value: b.building })))
const roomOptions = computed(() => {
  const b = (store.classroom.overview || []).find((x) => x.building === form.value.building)
  return (b?.rooms || []).map((r) => ({ label: r, value: r }))
})
watch(() => form.value.building, () => { form.value.room_no = '' })

function openUpload() {
  showUpload.value = true
  aiResult.value = null
  if (!form.value.building && buildingOptions.value.length) {
    form.value.building = buildingOptions.value[0].value
  }
}
function pickFile() { fileInput.value?.click() }
function onFile(e) {
  const f = e.target.files?.[0]
  if (!f) return
  if (!/^image\//.test(f.type)) { message.error('请选择图片文件'); return }
  photoFile.value = f
  aiResult.value = null
  const reader = new FileReader()
  reader.onload = () => { photoPreview.value = reader.result }
  reader.readAsDataURL(f)
}
function resetPhoto() {
  photoFile.value = null
  photoPreview.value = ''
  aiResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

/* AI 识图：上传图片 → deepseek-vl 判定 → 回填状态 */
async function runRecognize() {
  if (!photoFile.value) { message.warning('请先选择照片'); return }
  recognizing.value = true
  aiResult.value = null
  try {
    const res = await store.recognizeClassroomPhoto({
      photo: photoFile.value, building: form.value.building || null,
      room_no: form.value.room_no || null, save_log: false,
    })
    const r = res.recognition || {}
    aiResult.value = r
    if (r.status === 'free' || r.status === 'busy') form.value.status = r.status
    message.success(`AI 判定：${r.status === 'free' ? '空闲' : r.status === 'busy' ? '占用' : '未知'}（置信度 ${Math.round((r.confidence || 0) * 100)}%）`)
  } catch (err) {
    message.error('AI 识图失败：' + err.message)
  } finally {
    recognizing.value = false
  }
}

/* ── 教室使用可视化：每栋教学楼一张图（Y=楼层，X=教室序号），按所选时段着色 ── */
const DAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const campus = computed(() => store.classroom.campus)
const selDay = ref(new Date().getDay() === 0 ? 6 : new Date().getDay() - 1)  // 0~6 → 周一~周日
const selHour = ref(10)

const dayOptions = DAY_CN.map((d, i) => ({ label: d, value: i }))
const hourOptions = computed(() => (campus.value.hours || []).map((h) => ({ label: `${h}:00`, value: h })))

async function loadCampus() {
  try { await store.loadCampusUsage() }
  catch (err) { message.error('加载失败：' + err.message) }
}
watch(() => store.classroom.overview, (ov) => { if (ov && ov.length && !campus.value.buildings.length) loadCampus() }, { immediate: true })

/* 每栋楼 → 楼层行（高层在上）→ 每行 10 个教室格子 */
const buildingCharts = computed(() => {
  const hours = campus.value.hours || []
  const hi = hours.indexOf(selHour.value)
  return (campus.value.buildings || []).map((b) => {
    const floors = new Map()
    for (const r of b.rooms) {
      const fl = r.floor ?? parseInt((r.room_no.split('#')[1] || '0')[0], 10) ?? 1
      const seq = (r.room_no.match(/(\d{2})$/) || [])[1] || r.room_no
      const state = hi >= 0 ? r.matrix[selDay.value]?.[hi] ?? null : null
      if (!floors.has(fl)) floors.set(fl, [])
      floors.get(fl).push({ seq, room: r, state, building: b.building })
    }
    const rows = [...floors.entries()]
      .sort((a, x) => x[0] - a[0])
      .map(([floor, cells]) => ({ floor, cells: cells.sort((c, d) => c.seq.localeCompare(d.seq)) }))
    const known = b.rooms.reduce((a, r) => a + (r.samples || 0), 0)
    return { building: b.building, rows, known, total: b.rooms.length }
  })
})

function cellStyle(state) {
  if (state === 'free') return { background: 'rgba(74, 222, 128, 0.85)', boxShadow: '0 0 6px rgba(74,222,128,0.35)' }
  if (state === 'busy') return { background: 'rgba(248, 113, 113, 0.85)', boxShadow: '0 0 6px rgba(248,113,113,0.35)' }
  return { background: 'rgba(107,114,128,0.14)' }
}
function cellTitle(c) {
  const label = c.state === 'free' ? '空闲' : c.state === 'busy' ? '使用' : '未知'
  return `${c.room.room_no} · ${DAY_CN[selDay.value]} ${selHour.value}:00 ${label}（点击查看使用详情）`
}

/* ── 点击教室格子：浮动面板展示该教室当前时段的上课信息 ──
   ① 先完成数据请求再显示面板（无空白/加载闪烁）
   ② 面板锚定点击格子定位并自动避让视口边缘
   ③ 请求序号防竞态：频繁点击不同格子时旧响应直接丢弃 */
const popRef = ref(null)
const popVisible = ref(false)
const popMounted = ref(false)
const popStyle = ref({ left: '0px', top: '0px' })
const usageData = ref(null)
const usageRoom = ref('')
let popSeq = 0
let popAnchor = null

function placePanel() {
  const rect = popAnchor
  const el = popRef.value
  if (!rect || !el) return
  const pw = el.offsetWidth || 320
  const ph = el.offsetHeight || 240
  let left = rect.left + rect.width / 2 - pw / 2
  let top = rect.bottom + 10
  if (top + ph > window.innerHeight - 10) top = rect.top - ph - 10   // 下方放不下 → 翻到上方
  if (top < 10) top = 10
  left = Math.min(Math.max(10, left), window.innerWidth - pw - 10)
  popStyle.value = { left: `${left}px`, top: `${top}px` }
}

async function openUsage(c, ev) {
  const seq = ++popSeq
  popAnchor = ev.currentTarget.getBoundingClientRect()
  usageRoom.value = `${c.building} ${c.room.room_no}`
  if (popMounted.value) popVisible.value = false   // 面板已开 → 先淡出，避免旧数据错乱
  try {
    // 把「查看时段」的星期换算成本周对应日期
    const d = new Date()
    const isoToday = d.getDay() === 0 ? 7 : d.getDay()
    d.setDate(d.getDate() + (selDay.value + 1 - isoToday))
    const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const data = await store.roomUsageAt(c.building, c.room.room_no, day, selHour.value)
    if (seq !== popSeq) return   // 已有更新的点击，丢弃过期响应
    usageData.value = data
    popMounted.value = true
    requestAnimationFrame(() => { placePanel(); popVisible.value = true })
  } catch (err) {
    if (seq !== popSeq) return
    message.error('加载详情失败：' + err.message)
    closeUsage()
  }
}
function closeUsage() {
  popSeq++            // 使进行中的请求作废
  popVisible.value = false
  setTimeout(() => { if (!popVisible.value) popMounted.value = false }, 200)
}
function onDocClick(e) {
  if (!popVisible.value) return
  if (popRef.value?.contains(e.target)) return
  if (e.target.closest?.('.g-cell')) return   // 点其它格子由 openUsage 接管
  closeUsage()
}
function onKeydown(e) { if (e.key === 'Escape') closeUsage() }
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeydown)
  loadRecords()
  loadScheduleList()
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})

/* 提交上报（带照片存证） */
async function submitReport() {
  if (!photoFile.value) { message.warning('请先选择照片'); return }
  if (!form.value.building || !form.value.room_no) { message.warning('请选择教学楼与教室'); return }
  uploading.value = true
  try {
    await store.reportClassroomPhoto({
      photo: photoFile.value, building: form.value.building,
      room_no: form.value.room_no, status: form.value.status, note: form.value.note || null,
    })
    message.success('上报成功，热力图与采集记录已更新')
    showUpload.value = false
    resetPhoto()
    form.value.note = ''
  } catch (err) {
    message.error('上报失败：' + err.message)
  } finally {
    uploading.value = false
  }
}

const stats = computed(() => {
  const bs = campus.value.buildings || []
  const allCells = bs.flatMap((b) => b.rooms.flatMap((r) => r.matrix.flat()))
  const known = allCells.filter((c) => c !== null)
  const free = known.filter((c) => c === 'free').length
  return {
    avgFree: known.length ? Math.round((free / known.length) * 100) : 0,
    buildingCount: bs.length,
    roomCount: bs.reduce((a, b) => a + b.rooms.length, 0),
    samples: bs.reduce((a, b) => a + b.rooms.reduce((x, r) => x + (r.samples || 0), 0), 0),
  }
})

/* 预测柱状图：各教室空闲置信度 */
const predictOption = computed(() => ({
  grid: { left: 110, right: 30, top: 14, bottom: 20 },
  xAxis: { type: 'value', max: 100, ...axisBase(), splitLine: { lineStyle: { color: 'rgba(42,42,42,0.7)' } } },
  yAxis: { type: 'category', data: store.classroom.predict.map((r) => r.room), ...axisBase(), splitLine: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
  tooltip: { trigger: 'axis', backgroundColor: '#1e1e1e', borderColor: '#2a2a2a', textStyle: { color: '#e5e7eb', fontSize: 12 } },
  series: [
    {
      ...glowBar(store.settings.accent),
      data: store.classroom.predict.map((r) => r.free),
      barWidth: 14,
      itemStyle: { borderRadius: [0, 6, 6, 0], color: store.settings.accent, shadowColor: store.settings.accent + '99', shadowBlur: 12 },
      label: { show: true, position: 'right', color: '#9ca3af', fontSize: 11, formatter: '{c}%' },
    },
  ],
}))
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>空教室</h2>
      <span class="sub mono">CLASSROOM · 拍照采集 + 规律学习 + 空闲预测</span>
      <span class="spacer" />
      <input ref="excelInput" type="file" accept=".xlsx,.xls" multiple style="display:none" @change="onExcelFile" />
      <input ref="usageInput" type="file" accept=".xlsx,.xls" style="display:none" @change="onUsageExcelFile" />
      <input ref="parseInput" type="file" accept=".xlsx,.xls" multiple style="display:none" @change="onParseFiles" />
      <NButton size="small" type="info" ghost :loading="importing" @click="pickExcel">⬆ 导入教室课表 Excel</NButton>
      <NButton size="small" quaternary :loading="parsing" title="批量解析多个教室课表文件，校验编码与文件对应关系，可导出 xlsx/json" @click="pickParseFiles">🔍 解析检查</NButton>
      <NButton size="small" type="success" ghost :loading="usageImporting" @click="pickUsageExcel">📋 导入使用信息 Excel</NButton>
      <NButton size="small" quaternary @click="downloadUsageTemplate">模板</NButton>
      <NButton size="small" quaternary @click="openManage">🏫 教室管理</NButton>
      <NButton size="small" type="primary" ghost @click="openUpload">📷 上传教室照片</NButton>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <div class="col-3 stat-card">
        <div class="num-big">{{ stats.avgFree }}%</div>
        <div class="label-3">已采集时段空闲占比</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#60a5fa; text-shadow:0 0 14px #60a5fa66">{{ stats.buildingCount }}</div>
        <div class="label-3">教学楼数（每栋一张图）</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#f87171; text-shadow:0 0 14px #f8717166">{{ stats.roomCount }}</div>
        <div class="label-3">全校教室总数</div>
      </div>
      <div class="col-3 stat-card">
        <div class="num-big" style="color:#c084fc; text-shadow:0 0 14px #c084fc66">{{ stats.samples }}</div>
        <div class="label-3">历史快照样本</div>
      </div>
    </div>

    <div class="sched-bar card">
      <span class="sb-icon">🗂</span>
      <span class="sb-title">教室课表数据源</span>
      <template v-if="schedList.total">
        <span class="sb-text">已导入 <b>{{ schedList.total }}</b> 门课 · <b>{{ schedList.total_slots }}</b> 条排课 · 覆盖 <b>{{ schedList.room_locations }}</b> 个教室地点（仅用于占用预测，不出现在个人课程表）</span>
      </template>
      <span v-else class="sb-text dim">尚未导入教室课表。上传全校/教学楼课表 Excel 后，有课时段将自动标红。</span>
      <span class="spacer" />
      <NPopconfirm v-if="schedList.total" @positive-click="clearSchedule">
        <template #trigger>
          <NButton size="tiny" quaternary type="error" :loading="clearingSchedule">清空</NButton>
        </template>
        确定清空全部教室课表数据？个人课表不受影响。
      </NPopconfirm>
    </div>

    <div class="grid" style="margin-bottom: 16px">
      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">
            ▤ 教室使用情况可视化
            <span class="en">ROOM USAGE · 楼层 × 教室</span>
          </div>
          <div class="usage-ctrl">
            <span class="ctrl-label">查看时段</span>
            <NSelect v-model:value="selDay" size="tiny" class="ctrl-day" :options="dayOptions" />
            <NSelect v-model:value="selHour" size="tiny" class="ctrl-hour" :options="hourOptions" />
          </div>
        </header>
        <div class="legend">
          <span class="lg"><i class="sw" style="background:rgba(74,222,128,0.85);box-shadow:0 0 8px #4ade80" />空闲</span>
          <span class="lg"><i class="sw" style="background:rgba(248,113,113,0.85)" />使用</span>
          <span class="lg"><i class="sw" style="background:rgba(107,114,128,0.25)" />未知</span>
          <span class="lg-note mono">{{ DAY_CN[selDay] }} {{ selHour }}:00 各教学楼教室状态</span>
        </div>
        <div v-if="store.classroom.campusLoading && !campus.buildings.length" class="usage-empty">加载中…</div>
        <div v-else-if="!campus.buildings.length" class="usage-empty">暂无教室数据</div>
        <div v-else class="building-list">
          <div v-for="b in buildingCharts" :key="b.building" class="b-chart">
            <div class="b-head">
              <span class="b-name">{{ b.building }}</span>
              <span class="b-meta mono">{{ b.total }} 间 · 样本 {{ b.known }}</span>
            </div>
            <div class="b-grid" :style="{ gridTemplateColumns: `28px repeat(10, 1fr)` }">
              <div class="g-corner mono"></div>
              <div v-for="n in 10" :key="n" class="g-seq mono">{{ n }}</div>
              <div v-for="row in b.rows" :key="row.floor" class="g-floor-row">
                <div class="g-floor mono">{{ row.floor }}F</div>
                <div v-for="c in row.cells" :key="c.seq" class="g-cell clickable" :style="cellStyle(c.state)"
                     :title="cellTitle(c)" @click.stop="openUsage(c, $event)">
                  <span class="g-num mono">{{ c.seq }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <footer class="heat-foot mono">每栋教学楼一张图：纵轴=楼层（顶到底），横轴=教室序号（1-10）；红=该时段有课，绿=已导入该教室课表且此时段无课，灰=未知（未导入课表且无采集记录）。切换上方「查看时段」可看任意星期/时刻全校占用分布。</footer>
      </section>

      <section class="col-4 card">
        <header class="card-head"><div class="card-title">✦ 空闲预测推荐 <span class="en">PREDICTION</span></div></header>
        <GlowChart :option="predictOption" height="200px" />
        <div class="predict-list">
          <div
            v-for="p in store.classroom.predict" :key="p.room"
            class="p-row" :class="{ on: picked === p.room }"
            @click="picked = p.room"
          >
            <span class="dot" :class="p.free > 75 ? 'dot-green' : p.free > 60 ? 'dot-yellow' : 'dot-red'" />
            <div class="p-mid">
              <div class="p-room">{{ p.room }}</div>
              <div class="p-meta mono">{{ p.last }} · 样本 {{ p.samples }}</div>
            </div>
            <div class="p-free mono">{{ p.free }}%</div>
          </div>
        </div>
      </section>
    </div>

    <div class="grid">
      <section class="col-8 card">
        <header class="card-head">
          <div class="card-title">☰ 采集记录 <span class="en">SNAPSHOT LOG</span></div>
          <div class="rec-filters">
            <NSelect v-model:value="recBuilding" size="tiny" clearable placeholder="全部教学楼"
                     style="width:130px" :options="buildingOptions" />
            <NSelect v-model:value="recRoom" size="tiny" clearable placeholder="全部教室" filterable
                     style="width:130px" :options="recRoomOptions" :disabled="!recBuilding" />
            <span class="chip">{{ recData.total }} 条</span>
          </div>
        </header>
        <div class="rec-head mono">
          <span style="width:110px">时间</span><span style="flex:1">教室</span>
          <span style="width:70px">状态</span><span style="width:110px">来源</span>
          <span style="flex:1">备注</span><span style="width:56px">照片</span><span style="width:40px"></span>
        </div>
        <div v-if="recLoading" class="empty">加载中…</div>
        <template v-else>
          <div v-for="r in recData.items" :key="r.id ?? r.time" class="rec-row">
            <span class="mono c3" style="width:110px">{{ r.time }}</span>
            <span style="flex:1">{{ r.room }}</span>
            <span style="width:70px">
              <span class="chip" :class="r.state === '空闲' ? 'chip-accent' : 'chip-red'">{{ r.state }}</span>
            </span>
            <span class="c3" style="width:110px">{{ r.source }}</span>
            <span class="c3" style="flex:1">{{ r.note || '—' }}</span>
            <span style="width:56px">
              <span v-if="r.photo" class="photo-chip clickable" title="点击查看存证照片" @click="openPreview(r)">🖼</span>
              <span v-else class="c3">—</span>
            </span>
            <span style="width:40px">
              <NPopconfirm v-if="r.id" @positive-click="removeRecord(r)">
                <template #trigger>
                  <button class="rec-del" title="删除该记录">✕</button>
                </template>
                删除 {{ r.room }} {{ r.time }} 的采集记录？删除后预测样本将减少。
              </NPopconfirm>
            </span>
          </div>
          <div v-if="!recData.items.length" class="empty">该筛选条件下暂无采集记录，可通过照片上报或 Excel 导入积累数据</div>
          <div v-if="recTotalPages > 1" class="rec-pager">
            <button :disabled="recPage === 1" @click="gotoRecPage(recPage - 1)">‹ 上一页</button>
            <span class="mono">{{ recPage }} / {{ recTotalPages }}</span>
            <button :disabled="recPage === recTotalPages" @click="gotoRecPage(recPage + 1)">下一页 ›</button>
          </div>
        </template>
      </section>

      <section class="col-4 card tip-card">
        <header class="card-head"><div class="card-title">📷 如何提升预测准确度 <span class="en">HOW TO</span></div></header>
        <ol class="tips">
          <li>路过教室时用小程序拍一张照，标注「空闲 / 占用」</li>
          <li>同一教室同一时段累积 ≥ 2 个样本即可参与预测</li>
          <li>系统按时间衰减加权（近期样本权重更高）</li>
          <li>叠加本人课表：上课时段自动排除该教室</li>
          <li>连续采集 2 周后，预测命中率可达 85% 以上</li>
        </ol>
        <div class="mini-note mono">
          点击右上角「上传教室照片」即可采集：支持手动标注空闲/占用，或让 AI 识图自动判定，数据实时汇入热力图。
        </div>
      </section>
    </div>

    <!-- 照片上报 / AI 识图弹窗 -->
    <NModal v-model:show="showUpload" preset="card" title="📷 采集教室状态" style="width: 560px" :bordered="false">
      <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onFile" />
      <div class="drop" :class="{ has: photoPreview }" @click="pickFile">
        <img v-if="photoPreview" :src="photoPreview" class="preview" alt="预览" />
        <div v-else class="drop-hint">
          <div class="drop-ico">🖼</div>
          <div>点击选择教室照片（支持拍照后上传）</div>
        </div>
      </div>
      <div v-if="photoFile" class="file-bar">
        <span class="fname mono">{{ photoFile.name }}</span>
        <span class="spacer" />
        <NButton size="tiny" quaternary @click="resetPhoto">清除</NButton>
        <NButton size="tiny" type="info" :loading="recognizing" @click="runRecognize">✦ AI 识图判定</NButton>
      </div>

      <div v-if="aiResult" class="ai-box">
        <div class="ai-head mono">
          AI 判定：<b :class="aiResult.status === 'free' ? 'ok' : 'warn'">{{ aiResult.status === 'free' ? '空闲' : aiResult.status === 'busy' ? '占用' : '未知' }}</b>
          · 置信度 {{ Math.round((aiResult.confidence || 0) * 100) }}%
          <span v-if="aiResult.occupied_seats">· 就座约 {{ aiResult.occupied_seats }} 人</span>
        </div>
        <div v-if="aiResult.reason" class="ai-reason">{{ aiResult.reason }}</div>
        <div class="ai-tip mono">已按 AI 结果预选状态，可手动调整后提交</div>
      </div>

      <NForm label-placement="left" label-width="72" size="small" style="margin-top: 14px">
        <NFormItem label="教学楼">
          <NSelect v-model:value="form.building" :options="buildingOptions" placeholder="选择教学楼" />
        </NFormItem>
        <NFormItem label="教室">
          <NSelect v-model:value="form.room_no" :options="roomOptions" filterable tag placeholder="选择/输入教室号" />
        </NFormItem>
        <NFormItem label="状态">
          <NRadioGroup v-model:value="form.status">
            <NRadio value="free">空闲</NRadio>
            <NRadio value="busy">占用</NRadio>
          </NRadioGroup>
        </NFormItem>
        <NFormItem label="备注">
          <NInput v-model:value="form.note" placeholder="可选，如「自习人多」" />
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showUpload = false">取消</NButton>
          <NButton size="small" type="primary" :loading="uploading" @click="submitReport">提交上报</NButton>
        </div>
      </template>
    </NModal>

    <!-- 教室管理：列表 + 新增/编辑/停用/删除 -->
    <NModal v-model:show="showManage" preset="card" title="🏫 教室管理" style="width: 860px" :bordered="false">
      <div class="mg-bar">
        <NSelect v-model:value="manageBuilding" size="small" clearable placeholder="全部教学楼"
                 class="mg-building" :options="buildingOptions" @update:value="reloadRooms" />
        <NInput v-model:value="manageKeyword" size="small" placeholder="搜索教室编号…" style="width: 180px"
                @keyup.enter="reloadRooms" />
        <NButton size="small" quaternary @click="reloadRooms">搜索</NButton>
        <span class="spacer" />
        <span class="c3 mono" style="font-size:11px">{{ rooms.length }} 间</span>
        <NButton size="small" type="primary" @click="newRoom">＋ 新增教室</NButton>
      </div>
      <div v-if="manageLoading && !rooms.length" class="usage-empty">加载中…</div>
      <div v-else-if="!rooms.length" class="usage-empty">暂无教室，点击「新增教室」录入</div>
      <div v-else class="room-table">
        <div class="rt-head mono">
          <span style="width:120px">教学楼</span><span style="width:100px">编号</span>
          <span style="width:52px">楼层</span><span style="width:64px">容量</span>
          <span style="width:96px">类型</span><span style="width:110px">开放时间</span>
          <span style="width:70px">状态</span><span style="flex:1">操作</span>
        </div>
        <div v-for="r in rooms" :key="r.id" class="rt-row">
          <span style="width:120px">{{ r.building }}</span>
          <span style="width:100px" class="mono">{{ r.room_no }}</span>
          <span style="width:52px" class="mono c3">{{ r.floor ?? '—' }}F</span>
          <span style="width:64px" class="mono c3">{{ r.capacity }}</span>
          <span style="width:96px" class="c3">{{ r.room_type }}</span>
          <span style="width:110px" class="mono c3">{{ r.open_time }}-{{ r.close_time }}</span>
          <span style="width:70px">
            <span class="chip" :class="r.is_active ? 'chip-accent' : 'chip-red'">{{ r.is_active ? '启用' : '停用' }}</span>
          </span>
          <span style="flex:1; display:flex; gap:6px; justify-content:flex-end">
            <NButton size="tiny" quaternary @click="editRoom(r)">编辑</NButton>
            <NButton size="tiny" quaternary :type="r.is_active ? 'warning' : 'success'" @click="toggleRoomActive(r)">
              {{ r.is_active ? '停用' : '启用' }}
            </NButton>
            <NPopconfirm @positive-click="removeRoom(r)">
              <template #trigger><NButton size="tiny" quaternary type="error">删除</NButton></template>
              确定彻底删除 {{ r.building }} {{ r.room_no }}？（历史采集记录保留）
            </NPopconfirm>
          </span>
        </div>
      </div>
    </NModal>

    <!-- 教室新增/编辑表单 -->
    <NModal v-model:show="showRoomForm" preset="card" :title="roomEditing ? `✎ 编辑 ${roomEditing.building} ${roomEditing.room_no}` : '＋ 新增教室'"
            style="width: 520px" :bordered="false">
      <NForm label-placement="left" label-width="80" size="small">
        <div class="rf-grid">
          <NFormItem label="教学楼" required>
            <NSelect v-model:value="roomForm.building" :options="buildingOptions" filterable tag placeholder="选择/输入教学楼" />
          </NFormItem>
          <NFormItem label="教室编号" required>
            <NInput v-model:value="roomForm.room_no" placeholder="如 10#101" />
          </NFormItem>
          <NFormItem label="楼层">
            <NInput v-model:value="roomForm.floor" type="number" placeholder="留空按编号推断" />
          </NFormItem>
          <NFormItem label="容量">
            <NInput v-model:value="roomForm.capacity" type="number" placeholder="座位数" />
          </NFormItem>
          <NFormItem label="教室类型">
            <NSelect v-model:value="roomForm.room_type" :options="roomTypeOptions" />
          </NFormItem>
          <NFormItem label="开放时间">
            <div style="display:flex; gap:6px; align-items:center">
              <NInput v-model:value="roomForm.open_time" placeholder="07:00" style="width:80px" />
              <span class="c3">—</span>
              <NInput v-model:value="roomForm.close_time" placeholder="22:30" style="width:80px" />
            </div>
          </NFormItem>
          <NFormItem label="投影仪">
            <NSwitch v-model:value="roomForm.has_projector" size="small" />
          </NFormItem>
          <NFormItem label="空调">
            <NSwitch v-model:value="roomForm.has_ac" size="small" />
          </NFormItem>
        </div>
        <NFormItem label="备注">
          <NInput v-model:value="roomForm.note" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="可选" />
        </NFormItem>
      </NForm>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:10px">
          <NButton size="small" @click="showRoomForm = false">取消</NButton>
          <NButton size="small" type="primary" :loading="savingRoom" @click="saveRoom">保存</NButton>
        </div>
      </template>
    </NModal>

    <!-- 教室使用详情：锚定点击格子的浮动面板（数据就绪后才显示，带过渡动画） -->
    <Teleport to="body">
      <Transition name="pop">
        <div v-if="popMounted" ref="popRef" class="room-pop" :style="popStyle" :class="{ show: popVisible }">
          <div class="rp-head">
            <span class="rp-title">🪑 {{ usageRoom }}</span>
            <span class="rp-time mono">{{ usageData?.day }} {{ usageData?.at }} · {{ DAY_CN[selDay] }}</span>
            <span class="spacer" />
            <button class="rp-close" @click="closeUsage">✕</button>
          </div>

          <div class="rp-body">
            <!-- 该时段课程 -->
            <div v-if="usageData?.courses?.length" class="pop-sec">
              <div class="pop-label">当前时段课程（{{ usageData.courses.length }} 节）</div>
              <div v-for="(k, i) in usageData.courses" :key="i" class="rp-course">
                <div class="rc-head">
                  <b>{{ k.course_name }}</b>
                  <span class="chip">{{ k.course_type }}</span>
                </div>
                <div class="rc-meta mono">
                  {{ k.teacher || '教师未采集' }} · {{ k.start_time }}-{{ k.end_time }} · {{ k.weeks }}周{{ k.week_type !== '全周' ? k.week_type : '' }}
                </div>
                <div v-if="k.class_name" class="rc-meta mono">班级：{{ k.class_name }}</div>
                <div class="rc-meta mono c3">{{ k.location || '' }}</div>
              </div>
            </div>
            <div v-else-if="usageData" class="rp-empty">该时段暂无课程安排</div>

            <!-- Excel 使用记录 -->
            <div v-if="usageData?.current" class="pop-sec">
              <div class="pop-label">当前时段管理记录</div>
              <div class="pop-card" :class="usageData.current.status === 'free' ? 'is-free' : 'is-busy'">
                <div class="pc-head">
                  <span class="chip" :class="usageData.current.status === 'free' ? 'chip-accent' : 'chip-red'">
                    {{ usageData.current.status_label }}
                  </span>
                  <b>{{ usageData.current.start_time }} - {{ usageData.current.end_time }}</b>
                </div>
                <div v-if="usageData.current.department" class="pc-row">部门：{{ usageData.current.department }}</div>
                <div v-if="usageData.current.purpose" class="pc-row">用途：{{ usageData.current.purpose }}</div>
              </div>
            </div>

            <div v-if="usageData?.previous" class="pop-sec">
              <div class="pop-label">上次使用</div>
              <div class="pop-card is-busy">
                <div class="pc-head">
                  <span class="mono">{{ usageData.previous.use_date }}</span>
                  <b>{{ usageData.previous.start_time }} - {{ usageData.previous.end_time }}</b>
                </div>
                <div v-if="usageData.previous.department" class="pc-row">部门：{{ usageData.previous.department }}</div>
                <div v-if="usageData.previous.purpose" class="pc-row">用途：{{ usageData.previous.purpose }}</div>
              </div>
            </div>

            <div v-if="usageData?.day_records?.length" class="pop-sec">
              <div class="pop-label">当日全部安排（{{ usageData.day_records.length }} 条）</div>
              <div v-for="r in usageData.day_records" :key="r.id" class="pop-day-row">
                <span class="mono c3">{{ r.start_time }}-{{ r.end_time }}</span>
                <span class="chip" :class="r.status === 'free' ? 'chip-accent' : 'chip-red'">{{ r.status_label }}</span>
                <span class="pd-mid">{{ r.department || '—' }} {{ r.purpose || '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
    <!-- 采集记录照片预览 -->
    <NModal v-model:show="previewRec" preset="card" title="🖼 存证照片" style="width: 560px" :bordered="false">
      <div v-if="previewRec" class="pv-wrap">
        <img :src="previewRec.photoUrl" class="pv-img" :alt="previewRec.room" />
        <div class="pv-meta mono">
          {{ previewRec.room }} · {{ previewRec.time }} · {{ previewRec.state }} · {{ previewRec.source }}
          <span v-if="previewRec.note"> · {{ previewRec.note }}</span>
        </div>
      </div>
    </NModal>

    <!-- 教室课表解析检查结果 -->
    <NModal v-model:show="showParse" preset="card" title="🔍 教室课表 Excel 解析检查" style="width: 960px; max-width: 94vw" :bordered="false">
      <template v-if="parseResult">
        <div class="pz-summary">
          <span>文件 <b>{{ parseResult.summary.file_count }}</b></span>
          <span>无异常 <b class="ok">{{ parseResult.summary.ok_files }}</b></span>
          <span>课程条目 <b>{{ parseResult.summary.total_entries }}</b></span>
          <span>异常 <b :class="parseResult.summary.total_errors ? 'bad' : 'ok'">{{ parseResult.summary.total_errors }}</b></span>
          <span class="pz-rooms">教室：{{ parseResult.summary.rooms.join('、') || '—' }}</span>
          <span class="spacer" />
          <NButton size="tiny" type="info" ghost @click="exportParse('xlsx')">⬇ 导出 Excel</NButton>
          <NButton size="tiny" type="info" ghost @click="exportParse('json')">⬇ 导出 JSON</NButton>
        </div>
        <div class="pz-tabs">
          <span :class="{ on: parseTab === 'overview' }" @click="parseTab = 'overview'">文件概览</span>
          <span :class="{ on: parseTab === 'detail' }" @click="parseTab = 'detail'">解析明细（{{ parseRows.length }}）</span>
        </div>
        <div class="pz-body">
          <template v-if="parseTab === 'overview'">
            <div v-for="f in parseResult.files" :key="f.filename" class="pz-file" :class="{ bad: f.errors.length }">
              <div class="pf-head">
                <span class="pf-name">{{ f.filename }}</span>
                <span class="pf-code mono">{{ f.room_code || '未识别' }}</span>
                <span v-if="f.room_code" class="pf-deco mono">
                  {{ f.room_code.split('#')[0] }}号楼 · {{ f.room_code.split('#')[1][0] }}层 · {{ f.room_code.slice(-2) }}号
                </span>
                <span class="spacer" />
                <span class="pf-count">{{ f.entry_count || 0 }} 条</span>
                <span v-if="f.consistent" class="pf-tag ok">对应一致</span>
                <span v-else class="pf-tag bad">编码不一致</span>
              </div>
              <div class="pf-src mono" v-if="Object.keys(f.code_source || {}).length">
                <span v-for="(v, k) in f.code_source" :key="k">{{ k }}={{ v }}</span>
              </div>
              <div v-for="(e, i) in f.errors" :key="i" class="pf-err">⚠ {{ e }}</div>
            </div>
          </template>
          <table v-else class="pz-table">
            <thead>
              <tr><th>文件名</th><th>时间段</th><th>星期</th><th>课程名称</th><th>教师</th><th>周次</th><th>教室编码</th><th>楼号</th><th>楼层</th><th>序号</th></tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in parseRows" :key="i">
                <td class="mono ellip" :title="e.filename">{{ e.filename }}</td>
                <td class="mono">{{ e.time_range || e.section_label || '—' }}</td>
                <td>{{ e.weekday_cn }}</td>
                <td>{{ e.course }}</td>
                <td>{{ e.teacher || '—' }}</td>
                <td class="mono">{{ e.weeks || '—' }}</td>
                <td class="mono code">{{ e.room_code }}</td>
                <td>{{ e.building_no }}</td>
                <td>{{ e.floor }}</td>
                <td>{{ e.room_seq }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; min-width: 0; }
.stat-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }

.sched-bar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; margin-bottom: 16px; font-size: 13px; color: var(--text-2); }
.sched-bar .sb-icon { font-size: 16px; }
.sched-bar .sb-title { color: var(--text-1); font-weight: 600; white-space: nowrap; }
.sched-bar .sb-text b { color: #60a5fa; font-weight: 600; }
.sched-bar .sb-text.dim { color: var(--text-3); }

/* 解析检查弹窗 */
.pz-summary { display: flex; align-items: center; gap: 16px; font-size: 12.5px; color: var(--text-2); padding-bottom: 10px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.pz-summary b { color: var(--text-1); font-size: 15px; }
.pz-summary b.ok { color: #4ade80; }
.pz-summary b.bad { color: #f87171; }
.pz-rooms { color: var(--text-3); }
.pz-tabs { display: flex; gap: 6px; margin: 10px 0 8px; }
.pz-tabs span { font-size: 12px; color: var(--text-3); padding: 4px 12px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.pz-tabs span.on { color: var(--text-1); background: rgba(255,255,255,0.06); border-color: var(--border); }
.pz-body { max-height: 480px; overflow-y: auto; }
.pz-file { border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px; margin-bottom: 8px; }
.pz-file.bad { border-color: rgba(248,113,113,0.4); }
.pf-head { display: flex; align-items: center; gap: 10px; font-size: 12.5px; }
.pf-name { color: var(--text-1); font-weight: 600; }
.pf-code { color: #60a5fa; }
.pf-deco { color: var(--text-3); font-size: 11px; }
.pf-count { color: var(--text-2); font-size: 11.5px; }
.pf-tag { font-size: 10.5px; padding: 1px 8px; border-radius: 6px; }
.pf-tag.ok { color: #4ade80; background: rgba(74,222,128,0.1); }
.pf-tag.bad { color: #f87171; background: rgba(248,113,113,0.12); }
.pf-src { display: flex; gap: 14px; font-size: 10.5px; color: var(--text-3); margin-top: 4px; }
.pf-err { font-size: 11.5px; color: #f8bbd0; margin-top: 4px; }
.pz-table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.pz-table th { text-align: left; color: var(--text-3); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--card); }
.pz-table td { padding: 5px 8px; border-bottom: 1px dashed var(--border); color: var(--text-2); }
.pz-table td.code { color: #60a5fa; }
.pz-table .ellip { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 10px; }
.card-title { display: flex; align-items: center; gap: 8px; }
.room-select { width: 170px; }
.legend { display: flex; gap: 12px; }
.lg { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-3); }
.sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

.usage-empty { padding: 40px 0; text-align: center; color: var(--text-3); font-size: 12px; }
.usage-ctrl { display: flex; align-items: center; gap: 6px; }
.ctrl-label { font-size: 10px; color: var(--text-3); }
.ctrl-day { width: 72px; }
.ctrl-hour { width: 82px; }
.lg-note { font-size: 10px; color: var(--text-3); margin-left: 6px; }

.building-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; max-height: 620px; overflow-y: auto; padding-right: 4px; }
.b-chart { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 8px; padding: 9px 10px; }
.b-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 7px; }
.b-name { font-size: 12.5px; font-weight: 700; color: var(--text-1); }
.b-meta { font-size: 9.5px; color: var(--text-3); }
.b-grid { display: grid; gap: 2px; }
.g-corner { font-size: 8px; }
.g-seq { font-size: 8px; color: var(--text-3); text-align: center; }
.g-floor-row { display: contents; }
.g-floor { font-size: 9px; color: var(--text-2); display: flex; align-items: center; }
.g-cell { height: 20px; border-radius: 4px; display: grid; place-items: center; transition: transform 0.12s ease; }
.g-cell:hover { transform: scale(1.15); }
.g-cell.clickable { cursor: pointer; }
.g-num { font-size: 7.5px; color: rgba(255,255,255,0.5); }
.heat-foot { font-size: 10px; color: var(--text-3); margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 8px; }

/* 教室使用详情：锚定格子的浮动面板 */
.room-pop {
  position: fixed; z-index: 3000; width: 320px; max-width: calc(100vw - 20px);
  max-height: min(420px, calc(100vh - 24px)); overflow-y: auto;
  background: var(--card, #1e1e1e); border: 1px solid var(--border); border-radius: 12px;
  box-shadow: 0 12px 36px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03);
  opacity: 0; transform: translateY(8px) scale(0.97);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.room-pop.show { opacity: 1; transform: none; }
.pop-enter-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.pop-leave-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(8px) scale(0.97); }

.rp-head {
  position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; background: var(--card, #1e1e1e); border-bottom: 1px solid var(--border);
  border-radius: 12px 12px 0 0;
}
.rp-title { font-size: 13px; font-weight: 700; color: var(--text-1); white-space: nowrap; }
.rp-time { font-size: 10px; color: var(--text-3); }
.rp-close {
  border: none; background: transparent; color: var(--text-3); font-size: 13px;
  cursor: pointer; padding: 2px 6px; border-radius: 6px; line-height: 1;
}
.rp-close:hover { color: var(--text-1); background: rgba(255,255,255,0.08); }
.rp-body { display: flex; flex-direction: column; gap: 12px; padding: 12px; }

.rp-course { border: 1px solid var(--border); border-radius: 10px; padding: 9px 11px; background: rgba(96,165,250,0.05); }
.rc-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; color: var(--text-1); }
.rc-meta { font-size: 11px; color: var(--text-2); line-height: 1.7; }

.rp-empty { font-size: 12.5px; color: var(--text-3); text-align: center; padding: 14px 0; border: 1px dashed var(--border); border-radius: 10px; }

.pop-sec { display: flex; flex-direction: column; gap: 6px; }
.pop-label { font-size: 11px; color: var(--text-3); }
.pop-card { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; font-size: 12.5px; }
.pop-card.is-busy { border-color: rgba(248,113,113,0.35); background: rgba(248,113,113,0.05); }
.pop-card.is-free { border-color: rgba(74,222,128,0.35); background: rgba(74,222,128,0.05); }
.pc-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.pc-row { color: var(--text-2); line-height: 1.7; }
.pop-day-row { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 4px 0; border-bottom: 1px dashed var(--border); }
.pop-day-row:last-child { border-bottom: none; }
.pd-mid { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.predict-list { margin-top: 6px; }
.p-row { display: flex; align-items: center; gap: 10px; padding: 8px 8px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.p-row:hover { background: rgba(255, 255, 255, 0.03); }
.p-row.on { border-color: rgba(74, 222, 128, 0.4); background: rgba(74, 222, 128, 0.06); }
.p-mid { flex: 1; min-width: 0; }
.p-room { font-size: 12.5px; }
.p-meta { font-size: 10px; color: var(--text-3); margin-top: 2px; }
.p-free { font-size: 13px; color: var(--accent); }

.rec-head, .rec-row { display: flex; align-items: center; gap: 10px; padding: 8px 2px; font-size: 12px; }
.rec-head { color: var(--text-3); font-size: 10px; border-bottom: 1px solid var(--border); }
.rec-row { border-bottom: 1px dashed var(--border); }
.rec-row:last-child { border-bottom: none; }
.c3 { color: var(--text-3); }
.photo-chip { font-size: 13px; cursor: help; }
.photo-chip.clickable { cursor: pointer; }
.photo-chip.clickable:hover { filter: brightness(1.3); }
.rec-del { all: unset; cursor: pointer; font-size: 11px; color: var(--text-3); padding: 2px 6px; border-radius: 5px; }
.rec-del:hover { color: #f87171; background: rgba(248, 113, 113, 0.12); }
.empty { color: var(--text-3); font-size: 12px; padding: 16px 0; text-align: center; }
.rec-filters { display: flex; align-items: center; gap: 8px; }
.rec-pager { display: flex; align-items: center; justify-content: center; gap: 14px; padding: 10px 0 2px; font-size: 11.5px; color: var(--text-2); }
.rec-pager button {
  all: unset; cursor: pointer; padding: 3px 10px; border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-2); font-size: 11px;
}
.rec-pager button:hover:not(:disabled) { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.rec-pager button:disabled { opacity: 0.35; cursor: default; }
.pv-wrap { display: flex; flex-direction: column; gap: 8px; }
.pv-img { width: 100%; max-height: 380px; object-fit: contain; border-radius: 10px; border: 1px solid var(--border); background: #000; }
.pv-meta { font-size: 11px; color: var(--text-3); }

.tips { margin: 0; padding-left: 18px; color: var(--text-2); font-size: 12.5px; line-height: 1.9; }
.mini-note { font-size: 10px; color: var(--text-3); margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 8px; }
.mini-note em { color: var(--accent); font-style: normal; }

.drop { border: 1px dashed var(--border); border-radius: 12px; height: 180px; display: grid; place-items: center; cursor: pointer; overflow: hidden; background: rgba(255,255,255,0.02); transition: border-color .15s; }
.drop:hover { border-color: var(--accent); }
.drop.has { border-style: solid; }
.preview { width: 100%; height: 100%; object-fit: contain; }
.drop-hint { text-align: center; color: var(--text-3); font-size: 12.5px; }
.drop-ico { font-size: 30px; margin-bottom: 6px; opacity: .7; }
.file-bar { display: flex; align-items: center; gap: 10px; margin-top: 10px; font-size: 12px; }
.fname { color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
.ai-box { margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: rgba(96,165,250,0.07); border: 1px solid rgba(96,165,250,0.28); }
.ai-head { font-size: 12px; color: var(--text-2); }
.ai-head b.ok { color: var(--accent); }
.ai-head b.warn { color: #f87171; }
.ai-reason { font-size: 12px; color: var(--text-1); margin-top: 4px; line-height: 1.6; }
.ai-tip { font-size: 10px; color: var(--text-3); margin-top: 6px; }
.spacer { flex: 1; }

/* 教室管理 */
.mg-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.mg-building { width: 160px; }
.room-table { max-height: 480px; overflow-y: auto; }
.rt-head, .rt-row { display: flex; align-items: center; gap: 8px; padding: 7px 2px; font-size: 12px; }
.rt-head { color: var(--text-3); font-size: 10px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--card, #1e1e1e); z-index: 1; }
.rt-row { border-bottom: 1px dashed var(--border); }
.rt-row:last-child { border-bottom: none; }
.rt-row:hover { background: rgba(255,255,255,0.02); }
.rf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.rf-grid :deep(.n-form-item) { margin-bottom: 4px; }
</style>
