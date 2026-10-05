/** 接口层：按后端模块分组，页面只调用这里的方法。 */
import { http, streamChat } from './http'
import { saveBlob } from '../utils/download'

export { API_BASE, ApiError, clearAuth, getCachedUser, getToken, setCachedUser, setToken, streamChat } from './http'

/* ① 认证 */
export const authApi = {
  login: (username, password) => http.post('/auth/login', { username, password }),
  register: (payload) => http.post('/auth/register', payload),
  me: () => http.get('/auth/me'),
  updateMe: (payload) => http.put('/auth/me', payload),
  updateConfig: (config, merge = true) => http.put('/auth/me/config', { config, merge }),
  wxLogin: (code, nickname) => http.post('/auth/wx-login', { code, nickname }),
}

/* 总览 */
export const dashboardApi = {
  summary: (days = 7) => http.get('/dashboard/summary', { days }),
  alerts: (days = 7) => http.get('/dashboard/alerts', { days }),
  clearCache: () => http.post('/dashboard/cache/clear'),
}

/* ② 课程表 */
export const coursesApi = {
  semesters: () => http.get('/courses/semesters'),
  createSemester: (payload) => http.post('/courses/semesters', payload),
  updateSemester: (id, payload) => http.put(`/courses/semesters/${id}`, payload),
  setCurrentSemester: (id) => http.post(`/courses/semesters/${id}/current`),
  removeSemester: (id) => http.del(`/courses/semesters/${id}`),
  week: (week, semesterId = null) =>
    http.get('/courses/week', { week, semester_id: semesterId ?? undefined }),
  today: () => http.get('/courses/today'),
  list: (params) => http.get('/courses', params),
  create: (payload, force = false) => http.post('/courses', payload, { force }),
  update: (id, payload, force = false) => http.put(`/courses/${id}`, payload, { force }),
  remove: (id) => http.del(`/courses/${id}`),
  clear: (semesterId = null) => http.del('/courses', semesterId ? { semester_id: semesterId } : undefined),
  conflicts: (payload) => http.post('/courses/conflicts', payload),
  importJson: (payload) => http.post('/courses/import', payload),
  importExcel: (file, semesterId = null, force = false) =>
    http.upload('/courses/import-excel', file, { semester_id: semesterId, force }),
  /** 下载课表导入 Excel 模板（带鉴权的 blob 下载） */
  downloadImportTemplate: async () => {
    const resp = await fetch(`${API_BASE}/courses/import-template`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new ApiError('模板下载失败', resp.status)
    const blob = await resp.blob()
    await saveBlob(blob, '课表导入模板.xlsx')
  },
}

/* ③ DDL 任务 */
export const tasksApi = {
  list: (params) => http.get('/tasks', params),
  today: () => http.get('/tasks/today'),
  upcoming: (withinDays = 7, limit = 20) => http.get('/tasks/upcoming', { within_days: withinDays, limit }),
  stats: (days = 7) => http.get('/tasks/stats', { days }),
  categories: () => http.get('/tasks/categories'),
  create: (payload) => http.post('/tasks', payload),
  update: (id, payload) => http.put(`/tasks/${id}`, payload),
  remove: (id) => http.del(`/tasks/${id}`),
  complete: (id) => http.post(`/tasks/${id}/complete`),
  uncomplete: (id) => http.post(`/tasks/${id}/uncomplete`),
  addSubtask: (id, payload) => http.post(`/tasks/${id}/subtasks`, payload),
  updateSubtask: (subtaskId, payload) => http.put(`/tasks/subtasks/${subtaskId}`, payload),
  removeSubtask: (subtaskId) => http.del(`/tasks/subtasks/${subtaskId}`),
}

/* ④⑤ 空教室 */
export const classroomApi = {
  buildings: () => http.get('/classroom/buildings'),
  classrooms: (params) => http.get('/classroom/classrooms', params),
  createClassroom: (payload) => http.post('/classroom/classrooms', payload),
  updateClassroom: (id, payload) => http.put(`/classroom/classrooms/${id}`, payload),
  removeClassroom: (id, hard = false) => http.del(`/classroom/classrooms/${id}`, { hard }),
  overview: () => http.get('/classroom/overview'),
  freeRate: (building, roomNo, days = 120) =>
    http.get('/classroom/free-rate', { building, room_no: roomNo, days_back: days }),
  /** 教学楼使用状态图；opts: {on_date:'YYYY-MM-DD', week:number} 支持精确日期查询 */
  buildingUsage: (building, opts = {}) =>
    http.get('/classroom/building-usage', { building, days_back: opts.days_back ?? 120,
                                            on_date: opts.on_date, week: opts.week }),
  /** 全校使用状态图；opts: {on_date:'YYYY-MM-DD', week:number} */
  campusUsage: (opts = {}) =>
    http.get('/classroom/campus-usage', { days_back: opts.days_back ?? 120,
                                          on_date: opts.on_date, week: opts.week }),
  /** 学期信息（起始日对齐周一 + 某日期对应教学周） */
  semester: (onDate) => http.get('/classroom/semester', onDate ? { on_date: onDate } : undefined),
  predict: (weekday, hour, limit = 5) => http.get('/classroom/predict', { weekday, hour, limit }),
  today: () => http.get('/classroom/today'),
  recent: (limit = 10, extra = {}) => http.get('/classroom/status/recent', { limit, ...extra }),
  removeStatus: (id) => http.del(`/classroom/status/${id}`),
  report: (payload) => http.post('/classroom/status', payload),
  /** 带照片上报（multipart：photo + building/room_no/status/note/occupied_seats） */
  reportPhoto: ({ photo, building, room_no, status, note, occupied_seats }) => {
    const form = new FormData()
    form.append('photo', photo)
    form.append('building', building)
    form.append('room_no', room_no)
    form.append('status', status)
    if (note) form.append('note', note)
    form.append('occupied_seats', String(occupied_seats ?? 0))
    return http.uploadForm('/classroom/status/photo', form)
  },
  recognize: (payload) => http.post('/classroom/recognize', payload),
  /** AI 识图判定（multipart 直传图片，save_log=true 时自动落库） */
  recognizeUpload: ({ photo, building, room_no, save_log = true }) => {
    const form = new FormData()
    form.append('photo', photo)
    if (building) form.append('building', building)
    if (room_no) form.append('room_no', room_no)
    form.append('save_log', String(save_log))
    return http.uploadForm('/classroom/recognize/upload', form)
  },
  /** 导入教室课表 Excel（支持多选文件；后端按教室粒度替换旧数据） */
  importScheduleExcel: (files) => {
    const form = new FormData()
    ;(Array.isArray(files) ? files : [files]).forEach((f) => form.append('files', f))
    return http.uploadForm('/classroom/schedule/import-excel', form)
  },
  /** 已导入的教室课表清单 */
  scheduleList: () => http.get('/classroom/schedule'),
  /** 教室课表 Excel 解析检查（批量，不落库） */
  parseScheduleExcel: (files) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return http.uploadForm('/classroom/schedule/parse', form)
  },
  /** 解析结果导出为 xlsx / json 文件下载 */
  exportScheduleParse: async (files, fmt) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const resp = await fetch(`${API_BASE}/classroom/schedule/parse?export=${fmt}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: form,
    })
    if (!resp.ok) throw new ApiError('导出失败', resp.status)
    const blob = await resp.blob()
    await saveBlob(blob, `教室课表解析结果.${fmt}`)
  },
  /** 清空教室课表（不影响个人课表） */
  clearSchedule: () => http.del('/classroom/schedule'),
  /** 教室使用信息 Excel 导入（防重复录入） */
  importUsageExcel: (file) => {
    const form = new FormData()
    form.append('file', file)
    return http.uploadForm('/classroom/usage/import-excel', form)
  },
  /** 某教室指定时段使用详情（day: 'YYYY-MM-DD'；week 可选，缺省由日期换算） */
  usageAt: (building, room_no, day, hour, week) =>
    http.get('/classroom/usage-at', { building, room_no, day, hour, week }),
  /** 下载使用信息 Excel 模板（带鉴权的 blob 下载） */
  downloadUsageTemplate: async () => {
    const resp = await fetch(`${API_BASE}/classroom/usage/template`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new ApiError('模板下载失败', resp.status)
    const blob = await resp.blob()
    await saveBlob(blob, '教室使用信息模板.xlsx')
  },
}

/* ⑥ 学习记录 */
export const studyApi = {
  stats: (days = 7) => http.get('/study/stats', { days }),
  progress: (days = 7) => http.get('/study/progress', { days }),
  records: (params) => http.get('/study/records', params),
  create: (payload) => http.post('/study/records', payload),
  update: (id, payload) => http.put(`/study/records/${id}`, payload),
  remove: (id) => http.del(`/study/records/${id}`),
  mockScores: (limit = 30) => http.get('/study/mock-scores', { limit }),
}

/* ⑦ 考研规划 */
export const kaoyanApi = {
  target: () => http.get('/kaoyan/target'),
  saveTarget: (payload) => http.put('/kaoyan/target', payload),
  patchTarget: (payload) => http.patch('/kaoyan/target', payload),
  gap: () => http.get('/kaoyan/gap-analysis'),
  score: (payload) => http.post('/kaoyan/scores', payload),
  progress: () => http.get('/kaoyan/progress'),
  generatePlan: (payload) => http.post('/kaoyan/plan/generate', payload),
  plans: () => http.get('/kaoyan/plans'),
  planTasks: (planDate) => http.get('/kaoyan/plan/tasks', planDate ? { plan_date: planDate } : undefined),
  updatePlanTask: (id, payload) => http.put(`/kaoyan/plan/tasks/${id}`, payload),
  createPlanTask: (payload) => http.post('/kaoyan/plan/tasks', payload),
  removePlanTask: (id) => http.del(`/kaoyan/plan/tasks/${id}`),
  createPhase: (payload) => http.post('/kaoyan/plans/phases', payload),
  updatePhase: (id, payload) => http.put(`/kaoyan/plans/phases/${id}`, payload),
  removePhase: (id) => http.del(`/kaoyan/plans/phases/${id}`),
  intel: (refresh = false) => http.get('/kaoyan/intel', refresh ? { refresh: true } : undefined),
}

/* ⑧ 知识库 */
export const knowledgeApi = {
  folders: () => http.get('/knowledge/folders'),
  createFolder: (payload) => http.post('/knowledge/folders', payload),
  updateFolder: (id, payload) => http.put(`/knowledge/folders/${id}`, payload),
  removeFolder: (id, deleteDocs = false) => http.del(`/knowledge/folders/${id}`, { delete_docs: deleteDocs }),
  docs: (params) => http.get('/knowledge/docs', params),
  doc: (id) => http.get(`/knowledge/docs/${id}`),
  createDoc: (payload) => http.post('/knowledge/docs', payload),
  updateDoc: (id, payload) => http.put(`/knowledge/docs/${id}`, payload),
  removeDoc: (id) => http.del(`/knowledge/docs/${id}`),
  vectorize: (id) => http.post(`/knowledge/docs/${id}/vectorize`),
  chunks: (id) => http.get(`/knowledge/docs/${id}/chunks`),
  search: (payload) => http.post('/knowledge/search', payload),
  qa: (payload) => http.post('/knowledge/qa', payload),
  stats: () => http.get('/knowledge/stats'),
  upload: (file, folderId, tags) => http.upload('/knowledge/upload', file, { folder_id: folderId, tags }),
}

/* ⑨ 财务 */
export const financeApi = {
  summary: (month) => http.get('/finance/summary', { month }),
  trend: (months = 6) => http.get('/finance/trend', { months }),
  studyAnalysis: (months = 6) => http.get('/finance/study-analysis', { months }),
  records: (params) => http.get('/finance/records', params),
  create: (payload) => http.post('/finance/records', payload),
  update: (id, payload) => http.put(`/finance/records/${id}`, payload),
  remove: (id) => http.del(`/finance/records/${id}`),
  budgets: (month) => http.get('/finance/budgets', { month }),
  setBudget: (payload) => http.post('/finance/budgets', payload),
  removeBudget: (id) => http.del(`/finance/budgets/${id}`),
}

/* ⑩ 健康 */
export const healthApi = {
  report: (days = 7) => http.get('/health/report', { days }),
  records: (days = 7) => http.get('/health/records', { days }),
  saveRecord: (payload) => http.post('/health/records', payload),
  updateRecord: (id, payload) => http.put(`/health/records/${id}`, payload),
  removeRecord: (id) => http.del(`/health/records/${id}`),
  settings: () => http.get('/health/settings'),
  saveSettings: (payload) => http.put('/health/settings', payload),
  heartbeat: (spentMinutes = 0) => http.post('/health/sedentary/heartbeat', { spent_minutes: spentMinutes }),
  takeBreak: (note) => http.post('/health/sedentary/break', { note }),
}

/* ⑪ 系统管理 */
export const systemApi = {
  runtime: () => http.get('/system/runtime'),
  tables: () => http.get('/system/tables'),
  configs: (publicOnly = false) => http.get('/system/configs', { public_only: publicOnly }),
  setConfig: (payload) => http.post('/system/configs', payload),
  backups: () => http.get('/system/backups'),
  createBackup: (scope = 'user', note) => http.post('/system/backups', { scope, note }),
  removeBackup: (id) => http.del(`/system/backups/${id}`),
  restoreBackup: (id) => http.post(`/system/backups/${id}/restore`, undefined, { confirm: true }),
}

/* ⑫ AI 助手 */
export const aiApi = {
  chat: (payload) => http.post('/ai/chat', payload),
  sessions: (limit = 30) => http.get('/ai/sessions', { limit }),
  createSession: (title) => http.post('/ai/sessions', undefined, { title }),
  session: (id) => http.get(`/ai/sessions/${id}`),
  removeSession: (id) => http.del(`/ai/sessions/${id}`),
  tools: () => http.get('/ai/tools'),
  callTool: (name, args = {}) => http.post('/ai/tools/call', { name, arguments: args }),
  status: () => http.get('/ai/status'),
  reindex: () => http.post('/ai/reindex'),
  llmConfig: () => http.get('/ai/config'),
  saveLlmConfig: (payload) => http.put('/ai/config', payload),
  testLlmConfig: (payload) => http.post('/ai/config/test', payload),
  usage: () => http.get('/ai/usage'),
  recentUsage: (limit = 20) => http.get('/ai/usage/recent', { limit }),
}

/* ⑭ PDF 教室课表 */
export const pdfScheduleApi = {
  /** 多文件上传解析：files 为 File[] */
  upload: (files) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return http.uploadForm('/pdf-schedule/upload', form)
  },
  uploads: (limit = 50) => http.get('/pdf-schedule/uploads', { limit }),
  detail: (id) => http.get(`/pdf-schedule/uploads/${id}`),
  remove: (id) => http.del(`/pdf-schedule/uploads/${id}`),
  entries: (params) => http.get('/pdf-schedule/entries', params),
  options: () => http.get('/pdf-schedule/options'),
}

/* ⑮ 地址中心（书签） */
export const bookmarkApi = {
  list: (params) => http.get('/bookmarks', params),
  create: (payload) => http.post('/bookmarks', payload),
  update: (id, payload) => http.put(`/bookmarks/${id}`, payload),
  click: (id) => http.post(`/bookmarks/${id}/click`),
  remove: (id) => http.del(`/bookmarks/${id}`),
}

/* ⑯ 新闻资讯 */
export const newsApi = {
  items: (params) => http.get('/news/items', params),
  categories: () => http.get('/news/categories'),
  detail: (id) => http.get(`/news/items/${id}`),
  setRead: (id, isRead) => http.post(`/news/items/${id}/read`, undefined, { is_read: isRead }),
  setStar: (id, starred) => http.post(`/news/items/${id}/star`, undefined, { is_starred: starred }),
  remove: (id) => http.del(`/news/items/${id}`),
  crawl: (force = false) => http.post('/news/crawl', undefined, { force }),
  crawlStatus: () => http.get('/news/crawl/status'),
  logs: (limit = 10) => http.get('/news/logs', { limit }),
  sources: () => http.get('/news/sources'),
  createSource: (payload) => http.post('/news/sources', payload),
  updateSource: (id, payload) => http.put(`/news/sources/${id}`, payload),
  removeSource: (id) => http.del(`/news/sources/${id}`),
}

/* ⑬ 微信订阅消息 */
export const wechatApi = {
  status: () => http.get('/wechat/status'),
  quota: () => http.get('/wechat/quota'),
  grant: (kind, times = 1) => http.post('/wechat/subscribe/quota', { kind, times }),
  test: (kind = 'ddl') => http.post('/wechat/push/test', { kind }),
  scan: () => http.post('/wechat/push/scan'),
  logs: (limit = 20) => http.get('/wechat/push-logs', { limit }),
}

export const healthCheck = () => fetch('/health').then((r) => r.json())
