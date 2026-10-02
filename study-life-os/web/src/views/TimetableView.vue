<script setup>
import { h, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { courseApi } from '../api'
import WeekTimetable from '../components/WeekTimetable.vue'

const message = useMessage()
const dialog = useDialog()

const tab = ref('grid')
const week = ref({ days: [] })
const courses = ref([])
const drawer = ref(false)
const editingId = ref(null)
const saving = ref(false)
const importJson = ref(false)
const importText = ref('')

const form = reactive({ name: '', teacher: '', location: '', color: '#00e5a0', remark: '', slots: [] })

const weekdayOpts = [1, 2, 3, 4, 5, 6, 7].map((v) => ({ label: `周${'日一二三四五六'[v === 7 ? 0 : v]}`, value: v }))

function newSlot() { return { weekday: 1, start_time: '08:00', end_time: '09:40', weeks_text: '1-18周', start_week: 1, end_week: 18 } }

async function load() {
  week.value = await courseApi.week()
  courses.value = await courseApi.list()
}
onMounted(load)

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', teacher: '', location: '', color: '#00e5a0', remark: '', slots: [newSlot()] })
  drawer.value = true
}
function openEdit(c) {
  editingId.value = c.id
  Object.assign(form, { ...c, slots: c.slots.map((s) => ({ ...s })) })
  drawer.value = true
}
function addSlot() { form.slots.push(newSlot()) }

async function doSave(force) {
  saving.value = true
  try {
    const payload = { name: form.name, teacher: form.teacher, location: form.location, color: form.color, remark: form.remark, slots: form.slots }
    if (editingId.value) await courseApi.update(editingId.value, payload, force)
    else await courseApi.create(payload, force)
    drawer.value = false
    message.success('课程已保存')
    await load()
  } catch (e) {
    if (e.response?.status === 409 && e.detail?.conflicts) {
      const conflicts = e.detail.conflicts
      dialog.warning({
        title: '检测到课程时间冲突',
        content: () => h('div', { class: 'mono', style: 'font-size:12px;line-height:1.8' },
          conflicts.map((c, i) => h('div', { key: i },
            `⚡ 周${'日一二三四五六'[c.slot.weekday === 7 ? 0 : c.slot.weekday]} ${c.slot.start_time}-${c.slot.end_time} 与《${c.conflict_course}》(${c.conflict_slot.start_time}-${c.conflict_slot.end_time}, ${c.location || '地点未定'}) 重叠`))),
        positiveText: '忽略冲突并保存',
        negativeText: '返回修改',
        onPositiveClick: () => doSave(true),
      })
    }
  } finally { saving.value = false }
}

async function removeCourse(c) {
  await courseApi.remove(c.id)
  message.success(`已删除《${c.name}》`)
  load()
}

async function submitJsonImport() {
  try {
    const parsed = JSON.parse(importText.value)
    const list = Array.isArray(parsed) ? parsed : parsed.courses
    const rep = await courseApi.importJson(list)
    message.success(`导入 ${rep.imported} 门课程${rep.conflicts.length ? `，${rep.conflicts.length} 处冲突` : ''}`)
    importJson.value = false
    load()
  } catch (e) {
    if (e instanceof SyntaxError) message.error('JSON 格式不正确')
  }
}

function excelRequest({ file, onFinish, onError }) {
  courseApi.importExcel(file.file)
    .then((rep) => { message.success(`Excel 导入 ${rep.imported} 门课程，冲突 ${rep.conflicts.length} 处`); importJson.value = false; load(); onFinish() })
    .catch((e) => { onError(); message.error('导入失败：' + (e.detail || e.message)) })
}

const columns = [
  { title: '课程', key: 'name' },
  { title: '教师', key: 'teacher', width: 90 },
  { title: '地点', key: 'location', width: 120 },
  {
    title: '上课时段', key: 'slots',
    render: (row) => h('div', { class: 'slot-chips' },
      row.slots.map((s) => h('span', { class: 'chip mono', key: s.id },
        `周${'日一二三四五六'[s.weekday === 7 ? 0 : s.weekday]} ${s.start_time}-${s.end_time}`))),
  },
  {
    title: '操作', key: 'ops', width: 130,
    render: (row) => h('div', { style: 'display:flex;gap:8px' }, [
      h('button', { class: 'link-btn', onClick: () => openEdit(row) }, '编辑'),
      h('button', { class: 'link-btn danger', onClick: () => removeCourse(row) }, '删除'),
    ]),
  },
]
</script>

<template>
  <div class="page">
    <n-space justify="space-between" align="center" style="margin-bottom: 12px">
      <n-tabs v-model:value="tab" type="segment" size="small" style="width: 260px">
        <n-tab-pane name="grid" tab="⌗ 网格视图" />
        <n-tab-pane name="list" tab="☰ 课程列表" />
      </n-tabs>
      <n-space>
        <n-button size="small" @click="importJson = true">导入课表</n-button>
        <n-button type="primary" size="small" @click="openCreate">＋ 新课程</n-button>
      </n-space>
    </n-space>

    <WeekTimetable v-show="tab === 'grid'" :days="week.days" />

    <n-data-table v-show="tab === 'list'" :columns="columns" :data="courses" size="small" :bordered="false" striped />

    <!-- 编辑抽屉 -->
    <n-drawer v-model:show="drawer" :width="480" placement="right">
      <n-drawer-content :title="editingId ? '编辑课程' : '新建课程'" closable>
        <n-form label-placement="top" size="small">
          <n-grid :cols="2" :x-gap="10">
            <n-gi><n-form-item label="课程名称"><n-input v-model:value="form.name" placeholder="如：高等数学" /></n-form-item></n-gi>
            <n-gi><n-form-item label="教师"><n-input v-model:value="form.teacher" /></n-form-item></n-gi>
            <n-gi><n-form-item label="上课地点/教室"><n-input v-model:value="form.location" placeholder="如：三教201" /></n-form-item></n-gi>
            <n-gi><n-form-item label="主题色"><n-color-picker v-model:value="form.color" :show-alpha="false" size="small" :modes="['hex']" /></n-form-item></n-gi>
          </n-grid>
          <div class="section-title">上课时段（保存时自动进行冲突检测）</div>
          <div v-for="(s, i) in form.slots" :key="i" class="slot-row">
            <n-select v-model:value="s.weekday" :options="weekdayOpts" style="width: 86px" size="small" />
            <n-time-picker v-model:formatted-value="s.start_time" format="HH:mm" value-format="HH:mm" size="small" style="width: 110px" />
            <span class="sep">→</span>
            <n-time-picker v-model:formatted-value="s.end_time" format="HH:mm" value-format="HH:mm" size="small" style="width: 110px" />
            <n-input v-model:value="s.weeks_text" size="small" placeholder="周次" style="width: 90px" />
            <n-button quaternary size="tiny" class="rm" @click="form.slots.splice(i, 1)">✕</n-button>
          </div>
          <n-button size="tiny" dashed @click="addSlot">＋ 添加时段</n-button>
          <n-form-item label="备注" style="margin-top: 14px"><n-input v-model:value="form.remark" /></n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button @click="drawer = false">取消</n-button>
            <n-button type="primary" :loading="saving" @click="doSave(false)">保存（含冲突检测）</n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>

    <!-- 导入 -->
    <n-modal v-model:show="importJson" preset="card" title="导入课表" style="width: 620px">
      <n-tabs type="line" size="small">
        <n-tab-pane name="excel" tab="Excel 文件">
          <div class="hint mono">列顺序：课程名 / 教师 / 地点 / 星期(1-7或周一) / 开始 / 结束 / 周次</div>
          <n-upload :custom-request="excelRequest" :show-file-list="false" accept=".xlsx,.xls">
            <n-button dashed block style="margin-top: 10px">⬆ 选择 .xlsx 课表文件</n-button>
          </n-upload>
        </n-tab-pane>
        <n-tab-pane name="json" tab="JSON">
          <n-input v-model:value="importText" type="textarea" :rows="10" class="mono"
            placeholder='[{"name":"高等数学","location":"三教201","slots":[{"weekday":1,"start_time":"08:00","end_time":"09:40"}]}]' />
          <n-button size="small" type="primary" style="margin-top: 10px" @click="submitJsonImport">导入</n-button>
        </n-tab-pane>
      </n-tabs>
    </n-modal>
  </div>
</template>

<style scoped>
.slot-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.sep { color: #4a617f; }
.rm { color: #ff5c7a; }
.hint { font-size: 11px; color: #7d93b2; margin-bottom: 8px; }
:deep(.chip) { display: inline-block; font-size: 10px; color: #8fd8bd; background: rgba(0,229,160,0.08); border: 1px solid rgba(0,229,160,0.25); border-radius: 4px; padding: 1px 6px; margin: 2px 4px 2px 0; }
:deep(.link-btn) { background: none; border: none; color: #00e5a0; cursor: pointer; font-size: 12px; padding: 0; }
:deep(.link-btn.danger) { color: #ff5c7a; }
:deep(.slot-chips) { display: flex; flex-wrap: wrap; }
</style>
