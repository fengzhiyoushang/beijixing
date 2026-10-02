import http from './http'

export const authApi = {
  register: (d) => http.post('/auth/register', d),
  login: (d) => http.post('/auth/login', d),
  me: () => http.get('/auth/me'),
}

export const courseApi = {
  list: () => http.get('/courses'),
  week: () => http.get('/courses/week'),
  today: () => http.get('/courses/today'),
  create: (d, force = false) => http.post(`/courses${force ? '?force=true' : ''}`, d),
  update: (id, d, force = false) => http.put(`/courses/${id}${force ? '?force=true' : ''}`, d),
  remove: (id) => http.delete(`/courses/${id}`),
  importJson: (courses) => http.post('/courses/import', { courses }),
  importExcel: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/courses/import-excel', fd)
  },
}

export const taskApi = {
  list: (params) => http.get('/tasks', { params }),
  stats: () => http.get('/tasks/stats'),
  upcoming: (days = 7) => http.get('/tasks/upcoming', { params: { days } }),
  create: (d) => http.post('/tasks', d),
  update: (id, d) => http.put(`/tasks/${id}`, d),
  complete: (id) => http.post(`/tasks/${id}/complete`),
  remove: (id) => http.delete(`/tasks/${id}`),
}

export const checkinApi = {
  create: (d) => http.post('/checkin', d),
  today: () => http.get('/checkin/today'),
  calendar: (month) => http.get('/checkin/calendar', { params: { month } }),
  stats: () => http.get('/checkin/stats'),
  remove: (id) => http.delete(`/checkin/${id}`),
}

export const classroomApi = {
  records: (params) => http.get('/classroom/records', { params }),
  buildings: () => http.get('/classroom/buildings'),
  pattern: (building, room) => http.get('/classroom/pattern', { params: { building, room } }),
  remove: (id) => http.delete(`/classroom/records/${id}`),
  checkinForm: { /* 采集入口在小程序端 */ },
}

export const predictApi = (weekday, hour) =>
  http.get('/classroom/predict', { params: { weekday, hour } })

export const kaoyanApi = {
  goal: () => http.get('/kaoyan/goal'),
  saveGoal: (d) => http.put('/kaoyan/goal', d),
  deleteGoal: () => http.delete('/kaoyan/goal'),
  gapAnalysis: () => http.post('/kaoyan/gap-analysis'),
  generatePlan: (d) => http.post('/kaoyan/plan/generate', d),
  addPhase: (d) => http.post('/kaoyan/phases', d),
  patchPhase: (id, d) => http.patch(`/kaoyan/phases/${id}`, d),
  deletePhase: (id) => http.delete(`/kaoyan/phases/${id}`),
  dailyTasks: (date) => http.get('/kaoyan/daily-tasks', { params: date ? { date } : {} }),
  addDailyTask: (d) => http.post('/kaoyan/daily-tasks', d),
  patchPlanTask: (id, d) => http.patch(`/kaoyan/tasks/${id}`, d),
  deletePlanTask: (id) => http.delete(`/kaoyan/tasks/${id}`),
  progress: () => http.get('/kaoyan/progress'),
  review: (days = 7) => http.post('/kaoyan/review', { days }),
}

export const knowledgeApi = {
  docs: (params) => http.get('/knowledge/docs', { params }),
  createDoc: (d) => http.post('/knowledge/docs', d),
  getDoc: (id) => http.get(`/knowledge/docs/${id}`),
  updateDoc: (id, d) => http.put(`/knowledge/docs/${id}`, d),
  deleteDoc: (id) => http.delete(`/knowledge/docs/${id}`),
  upload: (file, category) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/knowledge/upload', fd, { params: category ? { category } : {} })
  },
  qa: (question, top_k = 5) => http.post('/knowledge/qa', { question, top_k }),
  stats: () => http.get('/knowledge/stats'),
}

export const financeApi = {
  records: (params) => http.get('/finance/records', { params }),
  create: (d) => http.post('/finance/records', d),
  update: (id, d) => http.put(`/finance/records/${id}`, d),
  remove: (id) => http.delete(`/finance/records/${id}`),
  summary: (month) => http.get('/finance/summary', { params: month ? { month } : {} }),
  trend: (months = 6) => http.get('/finance/trend', { params: { months } }),
  budgets: (month) => http.get('/finance/budgets', { params: { month } }),
  setBudget: (d) => http.post('/finance/budgets', d),
  deleteBudget: (id) => http.delete(`/finance/budgets/${id}`),
}

export const healthApi = {
  log: (d) => http.post('/health/logs', d),
  logs: (params) => http.get('/health/logs', { params }),
  today: () => http.get('/health/today'),
  report: (days = 7) => http.get('/health/report', { params: { days } }),
  settings: () => http.get('/health/settings'),
  saveSettings: (d) => http.put('/health/settings', d),
  heartbeat: () => http.post('/health/sedentary-heartbeat', { client: 'web' }),
  takeBreak: () => http.post('/health/sedentary-break'),
}

export const dashboardApi = { summary: () => http.get('/dashboard/summary') }

export const aiApi = {
  chat: (d) => http.post('/ai/chat', d),
  sessions: () => http.get('/ai/sessions'),
  messages: (sid) => http.get(`/ai/sessions/${sid}/messages`),
  deleteSession: (sid) => http.delete(`/ai/sessions/${sid}`),
}

/** SSE 流式对话：onEvent(type, data)。返回 AbortController 供关闭。 */
export function streamChat({ message, sessionId, onEvent, onFinally }) {
  const ctrl = new AbortController()
  const run = async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    const resp = await fetch('/api/v1/ai/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message, session_id: sessionId, source: 'web' }),
      signal: ctrl.signal,
    })
    if (!resp.ok || !resp.body) {
      onEvent('error', { message: `HTTP ${resp.status}` })
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const part of parts) {
        const evMatch = part.match(/^event:\s*(\w+)/m)
        const dataMatch = part.match(/^data:\s*(.*)$/ms)
        if (evMatch && dataMatch) {
          try {
            onEvent(evMatch[1], JSON.parse(dataMatch[1]))
          } catch { /* 忽略坏包 */ }
        }
      }
    }
  }
  run().catch((e) => {
    if (e.name !== 'AbortError') onEvent('error', { message: String(e) })
  }).finally(() => onFinally && onFinally())
  return ctrl
}
