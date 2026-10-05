/**
 * 全局状态：真实后端数据适配器。
 *
 * 设计要点：把后端接口返回**适配成原型阶段各视图已使用的数据结构**，
 * 因此 DashboardView / CoursesView / NotesView / ClassroomView / KaoyanView /
 * KnowledgeView / FinanceView / HealthView / SettingsView 基本无需改数据绑定。
 *
 * 所有写操作（新建/完成任务、生成计划、记健康、记账、上报教室…）都调用真实接口，
 * 完成后 refresh() 重新拉取，保证 Web 与小程序看到同一份数据。
 */
import { computed, reactive } from 'vue'
import router from '../router'
import {
  aiApi, authApi, bookmarkApi, classroomApi, clearAuth, coursesApi, dashboardApi, financeApi, getCachedUser,
  getToken, healthApi, kaoyanApi, knowledgeApi, newsApi, pdfScheduleApi, setCachedUser, setToken, studyApi, systemApi,
  tasksApi, wechatApi,
} from '../api'

const WEEK_CN = ['一', '二', '三', '四', '五', '六', '日']
const PALETTE = ['#4ade80', '#60a5fa', '#c084fc', '#facc15', '#f87171', '#2dd4bf', '#fb923c']
const FALLBACK_WEATHER = { city: '武汉', text: '多云', icon: '⛅', temp: 22, range: '18~25℃', aqi: '良 46' }

const emptyTimetable = () => ({ hours: [], days: [], slots: [], week: 1, totalClasses: 0 })

export const store = reactive({
  /* ── 会话与运行态 ── */
  ready: false,
  loading: false,
  errors: [],
  profile: { name: '—', school: '—', role: '—', avatar: '北' },
  runtime: null,
  aiStatus: null,
  /* Token 真实用量（来自后端 ai_usage 台账，非估算展示） */
  tokenSummary: null,
  wx: { status: null, quota: null, logs: [] },

  /* ── 视图数据（与原型同结构）── */
  systemStatus: [],
  weather: { ...FALLBACK_WEATHER },
  todayCourses: [],
  todayDdls: [],
  milestones: [],
  studyOverview: {
    weekDays: [], hours: [], weekTotal: 0, weekDelta: '—',
    ddlDone: 0, ddlTotal: 0, ddlRate: 0,
    kaoyanProgress: 0, kaoyanTargetScore: 0, kaoyanCurrentScore: 0,
  },
  knowledgeStats: {
    docCount: 0, mastery: 0, newThisWeek: 0, wordTotal: 0,
    weekNewTrend: [], hotTags: [], ragCount: 0, chunkCount: 0, coverage: 0,
  },
  newsFeed: [],
  /* 地址中心（书签） */
  bookmarks: { items: [], categories: [], loading: false },
  /* 新闻资讯 */
  news: { items: [], categories: [], total: 0, loading: false, crawling: false, logs: [], sources: [] },
  weekTimetable: emptyTimetable(),
  notes: [],
  noteStats: {
    pending: 0, todayDue: 0, weekDone: 0, overdue: 0,
    doneTrend: { days: [], done: [], created: [] }, category: [],
  },
  classroom: {
    matrix: { hours: [], days: [], cells: [] },
    predict: [], predictHint: '', records: [], room: null, overview: [],
    usage: { building: '', hours: [], rooms: [] }, usageLoading: false,
    campus: { hours: [], buildings: [] }, campusLoading: false,
    schedule: { total: 0, total_slots: 0, room_locations: 0, items: [] },
  },
  pdfSchedule: {
    uploads: [], entries: [], options: { rooms: [], courses: [], teachers: [], course_types: [] },
    currentWeek: null, loading: false, uploading: false,
  },
  kaoyan: {
    school: '—', major: '—', examDate: null, totalTarget: 0, totalCurrent: 0,
    subjects: [], phases: [], dailyTasks: [], weeklyReview: '', focusSubjects: [],
  },
  // 考研情报（聚焦爬虫：历年分数线 / 复试 / 就业），整体替换，视图用 computed 引用
  kaoyanIntel: { loading: false, loaded: false, data: null },
  knowledgeDocs: [],
  folders: [],
  foldersRaw: [],
  semesters: [],
  semesterRaw: [],
  classroomRooms: [],
  finance: {
    month: '', income: 0, expense: 0, studyExpense: 0, studyRatio: 0, balance: 0,
    categories: [], trend: { months: [], expense: [], study: [], income: [] },
    budgets: [], records: [],
  },
  health: {
    sedentary: { minutes: 0, interval: 45, shouldBreak: false, todayBreaks: 0, quiet: '—' },
    sedentaryEnabled: true,
    lastSleep: { hours: 0, bed: '—', up: '—', quality: '—' },
    weekSleep: { days: [], hours: [] },
    waterToday: 0, waterTarget: 2000, exerciseWeek: [], checkinStreak: 0, logs: [], tips: [],
  },
  settings: {
    accent: '#4ade80',
    accentPresets: [
      { name: '极光绿', value: '#4ade80' }, { name: '深海蓝', value: '#60a5fa' },
      { name: '赛博紫', value: '#c084fc' }, { name: '落日橙', value: '#fb923c' },
    ],
    /* ── 背景外观（「系统设置 → 背景外观」可自主配置） ── */
    appearance: {
      preset: 'aurora',      // 光晕配色预设 key
      glow: 100,             // 光晕强度 %（0~160）
      bgColor: '#070a08',    // 背景底色
      wallpaper: '',         // 自定义壁纸（dataURL，仅存本机）
      wallpaperDim: 45,      // 壁纸压暗 %（0~90）
      grid: 0,               // 网格纹理强度 %（0~40）
      radius: 18,            // 卡片圆角 px（8~26）
    },
    /* 背景光晕预设：三束光的位置/颜色固定，颜色可换 */
    bgPresets: [
      { key: 'aurora', name: '极光墨绿', hint: '默认：绿 + 冷蓝补光',
        glow: ['rgba(74,222,128,0.13)', 'rgba(74,222,128,0.09)', 'rgba(96,165,250,0.05)'] },
      { key: 'ocean', name: '深海蓝', hint: '冷静偏蓝，适合长时间阅读',
        glow: ['rgba(96,165,250,0.14)', 'rgba(56,189,248,0.09)', 'rgba(74,222,128,0.05)'] },
      { key: 'neon', name: '赛博紫', hint: '紫 + 品红，科技感更强',
        glow: ['rgba(192,132,252,0.14)', 'rgba(244,114,182,0.09)', 'rgba(96,165,250,0.06)'] },
      { key: 'sunset', name: '落日橙', hint: '暖橙光晕，夜间更柔和',
        glow: ['rgba(251,146,60,0.13)', 'rgba(251,191,36,0.08)', 'rgba(248,113,113,0.05)'] },
      { key: 'mono', name: '纯黑无光', hint: '关闭光晕，极致纯净',
        glow: ['rgba(255,255,255,0.00)', 'rgba(255,255,255,0.00)', 'rgba(255,255,255,0.00)'] },
    ],
    weatherCity: '武汉',
    dataSource: '—',
    backendUrl: '—',
    version: '—',
  },
  sidebarCollapsed: false,

  /* 派生：今日待推进（总览 DDL 卡片） */
  dashboardDdls: computed(() =>
    store.todayDdls.filter((t) => t.status === 'pending').slice(0, 5),
  ),

  /* ── 会话动作 ── */
  async login(username, password) {
    const data = await authApi.login(username, password)
    setToken(data.access_token)
    setCachedUser(data.user)
    await store.refresh()
    return data
  },

  async register(payload) {
    const data = await authApi.register(payload)
    setToken(data.access_token)
    setCachedUser(data.user)
    await store.refresh()
    return data
  },

  logout() {
    clearAuth()
    store.ready = false
    store.user = null
    router.replace('/login')
  },

  async bootstrap() {
    if (!getToken()) return false
    try {
      await store.refresh()
      return true
    } catch {
      return false
    }
  },

  /* ── 数据拉取 ── */
  async refresh() {
    store.loading = true
    const errors = []
    const safe = async (label, fn) => {
      try {
        return await fn()
      } catch (err) {
        errors.push(`${label}：${err.message}`)
        return null
      }
    }

    const [
      me, summary, week, taskList, taskStats, study14, plans, planTasks,
      kbStats, docs, folders, buildings, finSummary, finTrend, finBudgets, finRecords,
      healthReport, healthSettings, healthRecords, runtime, classroomRecent,
      wxStatus, wxQuota, wxLogs, aiStatus, tokenUsage,
    ] = await Promise.all([
      safe('用户信息', () => authApi.me()),
      safe('总览', () => dashboardApi.summary(7)),
      safe('周课表', () => coursesApi.week()),
      safe('任务列表', () => tasksApi.list({ limit: 100, order: 'priority' })),
      safe('任务统计', () => tasksApi.stats(14)),
      safe('学习统计', () => studyApi.stats(14)),
      safe('考研计划', () => kaoyanApi.plans()),
      safe('每日任务', () => kaoyanApi.planTasks()),
      safe('知识库统计', () => knowledgeApi.stats()),
      safe('文档列表', () => knowledgeApi.docs({ limit: 50 })),
      safe('文件夹', () => knowledgeApi.folders()),
      safe('教学楼', () => classroomApi.buildings()),
      safe('财务汇总', () => financeApi.summary()),
      safe('财务趋势', () => financeApi.trend(6)),
      safe('预算', () => financeApi.budgets()),
      safe('流水', () => financeApi.records({ limit: 60 })),
      safe('健康报告', () => healthApi.report(7)),
      safe('健康设置', () => healthApi.settings()),
      safe('健康记录', () => healthApi.records(14)),
      safe('系统运行态', () => systemApi.runtime()),
      safe('教室采集', () => classroomApi.recent(6)),
      safe('微信推送状态', () => wechatApi.status()),
      safe('订阅配额', () => wechatApi.quota()),
      safe('推送日志', () => wechatApi.logs(5)),
      safe('AI 状态', () => aiApi.status()),
      safe('Token 用量', () => aiApi.usage()),
    ])

    composeIdentity(me, runtime)
    composeWeather(me)
    composeCourses(summary)
    composeTimetable(week)
    composeTasks(summary, taskList, taskStats)
    composeStudy(summary, taskStats, study14, plans)
    composeKaoyan(summary, plans, planTasks)
    composeMilestones(summary, plans)
    composeKnowledge(kbStats, docs, folders)
    composeClassroom(buildings, classroomRecent)
    composeFinance(finSummary, finTrend, finBudgets, finRecords)
    composeHealth(healthReport, healthSettings, healthRecords, study14)
    composeAiAndStatus(summary, taskList, runtime, wxStatus, wxQuota, wxLogs, aiStatus)
    if (tokenUsage) store.tokenSummary = tokenUsage

    store.errors = errors
    store.loading = false
    store.ready = true
    applyAccent(store.settings.accent)
    loadLocalWallpaper()      // 本机壁纸 → appearance
    applyAppearance()         // 应用背景外观（预设/强度/底色/网格/圆角/壁纸）

    // 教室热力图需要按教室单独查询（二次请求）
    void composeClassroomMatrix(buildings)

    return !errors.length
  },

  /* ── 写操作（全部走真实接口）── */
  async addNote({ title, priority = 'medium', category = '学习', due = null, description = null }) {
    const task = await tasksApi.create({
      title, priority, category, description,
      due_at: due || null, tags: [category], source: 'web',
    })
    await store.refresh()
    return task
  },

  async toggleNote(id) {
    const note = store.notes.find((n) => n.id === id)
    const target = store.todayDdls.find((n) => n.id === id)
    const status = note?.status || target?.status || 'pending'
    if (status === 'done') await tasksApi.uncomplete(id)
    else await tasksApi.complete(id)
    await store.refresh()
  },

  async removeNote(id) {
    await tasksApi.remove(id)
    await store.refresh()
  },

  async updateNote(id, payload) {
    const task = await tasksApi.update(id, payload)
    await store.refresh()
    return task
  },

  async addSubtask(taskId, title) {
    const s = await tasksApi.addSubtask(taskId, { title })
    await store.refresh()
    return s
  },

  async toggleSubtask(subtaskId, done) {
    const s = await tasksApi.updateSubtask(subtaskId, { is_done: done })
    await store.refresh()
    return s
  },

  async removeSubtask(subtaskId) {
    const r = await tasksApi.removeSubtask(subtaskId)
    await store.refresh()
    return r
  },

  async addNews(tone, tag, text) {
    store.newsFeed.unshift({ time: '刚刚', tone, tag, text })
  },

  /* ── Token 用量（真实台账）── */
  async loadTokenUsage() {
    try {
      store.tokenSummary = await aiApi.usage()
    } catch { /* 离线时保留上次值 */ }
    return store.tokenSummary
  },
  /** 流式对话 done 事件直接带回最新汇总，免二次请求 */
  applyTokenSummary(summary) {
    if (summary && typeof summary.total_tokens === 'number') store.tokenSummary = summary
  },

  /* ── 个人资料（头像窗口内自定义）── */
  userRaw: null,
  async updateProfile(payload) {
    const user = await authApi.updateMe(payload)
    setCachedUser(user)
    await store.refresh()
    return user
  },
  async updateProfileConfig(config) {
    await authApi.updateConfig(config, true)
    await store.refresh()
  },

  /* ── 地址中心 ── */
  async loadBookmarks(params = {}) {
    store.bookmarks.loading = true
    try {
      const data = await bookmarkApi.list(params)
      store.bookmarks.items = data?.items || []
      store.bookmarks.categories = data?.categories || []
      return store.bookmarks.items
    } finally {
      store.bookmarks.loading = false
    }
  },
  async createBookmark(payload) {
    const b = await bookmarkApi.create(payload)
    await store.loadBookmarks()
    return b
  },
  async updateBookmark(id, payload) {
    const b = await bookmarkApi.update(id, payload)
    await store.loadBookmarks()
    return b
  },
  async removeBookmark(id) {
    const r = await bookmarkApi.remove(id)
    await store.loadBookmarks()
    return r
  },
  async clickBookmark(id) {
    try { await bookmarkApi.click(id) } catch { /* 计数失败不影响打开 */ }
  },

  /* ── 新闻资讯 ── */
  async loadNews(params = {}) {
    store.news.loading = true
    try {
      const [list, cats] = await Promise.all([newsApi.items(params), newsApi.categories()])
      store.news.items = list?.items || []
      store.news.total = list?.total || 0
      store.news.categories = cats?.items || []
      return store.news.items
    } finally {
      store.news.loading = false
    }
  },
  async newsCrawl(force = false) {
    const r = await newsApi.crawl(force)
    if (r?.started) store.news.crawling = true
    return r
  },
  async newsCrawlStatus() {
    const s = await newsApi.crawlStatus()
    store.news.crawling = !!s?.running
    if (!s?.running) {
      await store.loadNews({ limit: 60 })
      store.news.logs = (await newsApi.logs(8))?.items || []
    }
    return s
  },
  async loadNewsSources() {
    store.news.sources = (await newsApi.sources())?.items || []
    return store.news.sources
  },
  async newsSetRead(id, isRead) {
    await newsApi.setRead(id, isRead)
    const it = store.news.items.find((x) => x.id === id)
    if (it) it.is_read = isRead
  },
  async newsSetStar(id, starred) {
    await newsApi.setStar(id, starred)
    const it = store.news.items.find((x) => x.id === id)
    if (it) it.is_starred = starred
  },

  async setAccent(color) {
    store.settings.accent = color
    applyAccent(color)
    try {
      await authApi.updateConfig({ accent: color, theme: 'dark' }, true)
    } catch {
      /* 离线或未登录时仅本地生效 */
    }
  },

  /**
   * 更新背景外观（局部字段合并）。
   * 立即生效并写入账号配置；壁纸体积大，单独存本机 localStorage。
   * @param {object} patch 如 { preset:'ocean', glow:120, bgColor:'#05070a', grid:20, radius:14 }
   */
  async setAppearance(patch = {}) {
    store.settings.appearance = { ...store.settings.appearance, ...patch }
    applyAppearance()
    // 只把可序列化的轻量字段同步到后端（排除壁纸 dataURL）
    const { wallpaper, ...rest } = store.settings.appearance
    try {
      await authApi.updateConfig({ appearance: rest }, true)
    } catch {
      /* 离线时仅本地生效 */
    }
    return store.settings.appearance
  },

  /**
   * 设置自定义壁纸（传空字符串则清除）。
   * @param {string} dataUrl 图片 dataURL
   */
  async setWallpaper(dataUrl) {
    store.settings.appearance.wallpaper = dataUrl || ''
    try {
      if (dataUrl) localStorage.setItem(WALLPAPER_KEY, dataUrl)
      else localStorage.removeItem(WALLPAPER_KEY)
    } catch {
      /* 超配额时仅本次会话生效 */
    }
    applyAppearance()
    return store.settings.appearance.wallpaper
  },

  /** 恢复默认背景外观（含清除壁纸） */
  async resetAppearance() {
    store.settings.appearance = {
      preset: 'aurora', glow: 100, bgColor: '#070a08',
      wallpaper: '', wallpaperDim: 45, grid: 0, radius: 18,
    }
    try { localStorage.removeItem(WALLPAPER_KEY) } catch { /* 忽略 */ }
    applyAppearance()
    const { wallpaper, ...rest } = store.settings.appearance
    try { await authApi.updateConfig({ appearance: rest }, true) } catch { /* 忽略 */ }
    return store.settings.appearance
  },

  async setWeatherCity(city) {
    store.weather.city = city
    store.settings.weatherCity = city
    store.weather = { ...store.weather, city }
    try {
      await authApi.updateConfig({ weather_city: city }, true)
    } catch {
      /* 忽略 */
    }
  },

  /** 考研情报：聚焦爬虫抓取目标院校分数线/就业（force=重新抓取） */
  async loadKaoyanIntel(force = false) {
    if (store.kaoyanIntel.loading) return
    store.kaoyanIntel = { ...store.kaoyanIntel, loading: true }
    try {
      const data = await kaoyanApi.intel(force)
      store.kaoyanIntel = { loading: false, loaded: true, data: data || null }
    } catch {
      store.kaoyanIntel = { loading: false, loaded: true, data: null }
    }
  },

  async kaoyanGeneratePlan(payload = {}) {
    const result = await kaoyanApi.generatePlan({
      total_weeks: payload.totalWeeks ?? 16,
      daily_minutes: payload.dailyMinutes ?? 300,
      use_ai: payload.useAi ?? true,
      replace_existing: payload.replaceExisting ?? false,
    })
    await store.refresh()
    return result
  },

  /** 新增每日任务（归属某阶段） */
  async addKaoyanTask(payload) {
    const t = await kaoyanApi.createPlanTask(payload)
    await store.refresh()
    return t
  },

  async removeKaoyanTask(id) {
    const r = await kaoyanApi.removePlanTask(id)
    await store.refresh()
    return r
  },

  async createKaoyanPhase(payload) {
    const p = await kaoyanApi.createPhase(payload)
    await store.refresh()
    return p
  },

  async updateKaoyanPhase(id, payload) {
    const p = await kaoyanApi.updatePhase(id, payload)
    await store.refresh()
    return p
  },

  async removeKaoyanPhase(id) {
    const r = await kaoyanApi.removePhase(id)
    await store.refresh()
    return r
  },

  /** 录入/更新考研目标（院校、专业、初试日期、各科目标分与当前成绩） */
  async saveKaoyanTarget(payload) {
    const target = await kaoyanApi.saveTarget(payload)
    await store.refresh()
    return target
  },

  /** 录入某科最新成绩（自动重算总分与差距） */
  async recordKaoyanScore(payload) {
    const result = await kaoyanApi.score(payload)
    await store.refresh()
    return result
  },

  async toggleKaoyanTask(id, done) {
    await kaoyanApi.updatePlanTask(id, { is_done: done })
    await store.refresh()
  },

  async knowledgeAsk(question) {
    const result = await knowledgeApi.qa({ question, mode: 'auto', top_k: 5 })
    return result
  },

  async createDoc(payload) {
    const doc = await knowledgeApi.createDoc(payload)
    await store.refresh()
    return doc
  },

  /** 文档详情（含正文） */
  loadDoc(id) {
    return knowledgeApi.doc(id)
  },

  /** 新建/编辑文档（id 为空则新建） */
  async saveDoc(payload, { id = null } = {}) {
    const doc = id
      ? await knowledgeApi.updateDoc(id, { ...payload, re_vectorize: true })
      : await knowledgeApi.createDoc(payload)
    await store.refresh()
    return doc
  },

  async updateDoc(id, payload) {
    const doc = await knowledgeApi.updateDoc(id, { ...payload, re_vectorize: true })
    await store.refresh()
    return doc
  },

  async removeDoc(id) {
    await knowledgeApi.removeDoc(id)
    await store.refresh()
  },

  async addFinanceRecord(payload) {
    const record = await financeApi.create(payload)
    await store.refresh()
    return record
  },

  async updateFinanceRecord(id, payload) {
    const record = await financeApi.update(id, payload)
    await store.refresh()
    return record
  },

  async removeFinanceRecord(id) {
    const r = await financeApi.remove(id)
    await store.refresh()
    return r
  },

  async setFinanceBudget(payload) {
    const r = await financeApi.setBudget(payload)
    await store.refresh()
    return r
  },

  async removeFinanceBudget(id) {
    const r = await financeApi.removeBudget(id)
    await store.refresh()
    return r
  },

  /** 按月加载财务视图数据（汇总/预算/流水），趋势保持近 6 个月 */
  async loadFinanceMonth(month) {
    const [summary, budgets, records] = await Promise.all([
      financeApi.summary(month),
      financeApi.budgets(month),
      financeApi.records({ month, limit: 300 }),
    ])
    composeFinance(summary, { items: store.finance.trendRaw || [] }, budgets, records)
    store.finance.month = month
    return summary
  },

  async addHealthRecord(payload) {
    const record = await healthApi.saveRecord(payload)
    await store.refresh()
    return record
  },

  async saveHealthSettings(payload) {
    const result = await healthApi.saveSettings(payload)
    store.health.sedentary.interval = result.sedentary_interval_min
    store.health.waterTarget = result.target_water_ml
    return result
  },

  async updateHealthRecord(id, payload) {
    const record = await healthApi.updateRecord(id, payload)
    await store.refresh()
    return record
  },

  async removeHealthRecord(id) {
    const r = await healthApi.removeRecord(id)
    await store.refresh()
    return r
  },

  async sedentaryHeartbeat() {
    const status = await healthApi.heartbeat(0)
    store.health.sedentary = {
      ...store.health.sedentary,
      minutes: status.minutes_since_break,
      interval: status.interval_min,
      shouldBreak: status.should_break,
    }
    return status
  },

  async takeSedentaryBreak() {
    const result = await healthApi.takeBreak('Web 端已起身')
    store.health.sedentary = {
      ...store.health.sedentary,
      minutes: result.minutes_since_break,
      shouldBreak: result.should_break,
    }
    return result
  },

  async reportClassroom({ building, room_no, status, note = null }) {
    const log = await classroomApi.report({ building, room_no, status, note, source: 'web' })
    await store.refresh()
    return log
  },

  /** 教室照片上报（含存证照片）→ 刷新热力图与采集记录 */
  async reportClassroomPhoto(payload) {
    const log = await classroomApi.reportPhoto(payload)
    await store.refresh()
    return log
  },

  /** 删除一条采集记录 → 刷新 */
  async removeClassroomStatus(id) {
    const r = await classroomApi.removeStatus(id)
    await store.refresh()
    return r
  },

  /** AI 识图判定教室状态（自动落库）→ 刷新 */
  async recognizeClassroomPhoto(payload) {
    const result = await classroomApi.recognizeUpload(payload)
    await store.refresh()
    return result
  },

  /** 知识库文件上传（md/txt/docx/xlsx）→ 解析入库向量化 */
  async uploadKnowledgeDoc({ file, folderId = null, tags = null }) {
    const doc = await knowledgeApi.upload(file, folderId, tags)
    await store.refresh()
    return doc
  },

  /** 课表 Excel 批量导入 */
  async importCoursesExcel({ file, semesterId = null, force = false }) {
    const result = await coursesApi.importExcel(file, semesterId, force)
    await store.refresh()
    return result
  },

  async loadSemesters(semesterId = null) {
    try {
      const data = await coursesApi.semesters()
      const items = data?.items || data || []
      store.semesterRaw = items
      store.semesters = items.map((s) => ({ label: s.name, value: s.id, isCurrent: !!s.is_current }))
      // 切换学期：重新拉取该学期周课表
      if (semesterId !== undefined) {
        const week = await coursesApi.week(undefined, semesterId)
        composeTimetable(week)
      }
      return store.semesters
    } catch {
      return []
    }
  },

  async createSemester(payload) {
    const s = await coursesApi.createSemester(payload)
    await store.loadSemesters()
    await store.refresh()
    return s
  },

  async updateSemester(id, payload) {
    const s = await coursesApi.updateSemester(id, payload)
    await store.loadSemesters()
    await store.refresh()
    return s
  },

  async setCurrentSemester(id) {
    const s = await coursesApi.setCurrentSemester(id)
    await store.loadSemesters()
    await store.refresh()
    return s
  },

  async removeSemester(id) {
    const r = await coursesApi.removeSemester(id)
    await store.loadSemesters()
    await store.refresh()
    return r
  },

  /* ── 课程 CRUD（新建/编辑，force 忽略冲突）── */
  coursesRaw: [],
  async loadCourses(params = {}) {
    const data = await coursesApi.list(params)
    store.coursesRaw = data?.items || []
    return store.coursesRaw
  },

  async saveCourse(payload, { id = null, force = false } = {}) {
    const result = id
      ? await coursesApi.update(id, payload, force)
      : await coursesApi.create(payload, force)
    await store.refresh()
    return result
  },

  /** 冲突预检（不落库） */
  checkCourseConflicts(payload) {
    return coursesApi.conflicts(payload)
  },

  /* ── 教室信息 CRUD ── */
  async loadClassrooms(params = {}) {
    const data = await classroomApi.classrooms({ only_active: false, ...params })
    store.classroomRooms = data?.items || []
    return store.classroomRooms
  },

  async createClassroom(payload) {
    const room = await classroomApi.createClassroom(payload)
    await store.refresh()
    return room
  },

  async updateClassroom(id, payload) {
    const room = await classroomApi.updateClassroom(id, payload)
    await store.refresh()
    return room
  },

  async removeClassroom(id, hard = false) {
    const r = await classroomApi.removeClassroom(id, hard)
    await store.refresh()
    return r
  },

  /* ── 知识库文件夹 CRUD ── */
  async createFolder(payload) {
    const f = await knowledgeApi.createFolder(payload)
    await store.refresh()
    return f
  },

  async renameFolder(id, payload) {
    const f = await knowledgeApi.updateFolder(id, payload)
    await store.refresh()
    return f
  },

  async removeFolder(id, deleteDocs = false) {
    const r = await knowledgeApi.removeFolder(id, deleteDocs)
    await store.refresh()
    return r
  },

  /** 按文件夹筛选文档 */
  async loadDocsByFolder(folderId = null) {
    const data = await knowledgeApi.docs({ folder_id: folderId ?? undefined, limit: 200 })
    composeKnowledgeDocs(data)
    return store.knowledgeDocs
  },

  /**
   * 加载全校使用状态（每楼一张 楼层×教室序号 图）
   * @param {{on_date?: string, week?: number}} opts
   *   on_date：查询日期 YYYY-MM-DD（后端按该日期所在教学周精确匹配课表周次）
   *   week：直接指定教学周（优先于日期）
   */
  async loadCampusUsage(opts = {}) {
    store.classroom.campusLoading = true
    try {
      const data = await classroomApi.campusUsage(opts)
      store.classroom.campus = {
        hours: data.hours || [],
        buildings: data.buildings || [],
        semester: data.semester || null,
      }
      return data
    } finally {
      store.classroom.campusLoading = false
    }
  },

  /** 加载某教学楼全部教室的使用状态图（每间一张） */
  async loadBuildingUsage(building, opts = {}) {
    store.classroom.usageLoading = true
    try {
      const data = await classroomApi.buildingUsage(building, opts)
      store.classroom.usage = {
        building: data.building,
        hours: data.hours || [],
        rooms: data.rooms || [],
        semester: data.semester || null,
      }
      return data
    } finally {
      store.classroom.usageLoading = false
    }
  },

  /** 切换热力图教室 */
  async loadRoomHeat(building, roomNo) {
    store.classroom.heatSel = { building, room_no: roomNo }
    const rate = await classroomApi.freeRate(building, roomNo)
    store.classroom.matrix = {
      hours: rate.hours || [],
      days: WEEK_CN.map((d) => `周${d}`),
      cells: (rate.matrix || []).map((row) => row.map((cell) => (cell.rate === null ? -1 : cell.rate))),
    }
    store.classroom.matrixRoom = rate.name
    store.classroom.samples = rate.samples
    return rate
  },

  async createBackup() {
    return systemApi.createBackup('user', 'Web 端手动备份')
  },

  async listBackups() {
    const data = await systemApi.backups()
    return data?.items || []
  },

  async removeBackup(id) {
    return systemApi.removeBackup(id)
  },

  /* ── 微信订阅推送 ── */
  async wechatGrant(kind, times = 1) {
    const r = await wechatApi.grant(kind, times)
    await store.refresh()
    return r
  },

  async wechatTestPush(kind = 'ddl') {
    const r = await wechatApi.test(kind)
    await store.refresh()
    return r
  },

  async wechatScan() {
    const r = await wechatApi.scan()
    await store.refresh()
    return r
  },

  async createCourse(payload, force = false) {
    const created = await coursesApi.create(payload, force)
    await store.refresh()
    return created
  },

  async removeCourse(id) {
    await coursesApi.remove(id)
    await store.refresh()
  },

  /** 清空课程（撤销错误课表） */
  async clearCourses(semesterId = null) {
    const r = await coursesApi.clear(semesterId)
    await store.refresh()
    return r
  },

  /** 空教室页导入教室课表（支持多选文件；后端按教室粒度替换） */
  async importClassroomSchedule(files) {
    const result = await classroomApi.importScheduleExcel(files)
    await store.refresh()
    return result
  },
  /** 教室课表清单 */
  async loadClassroomSchedule() {
    store.classroom.schedule = await classroomApi.scheduleList()
    return store.classroom.schedule
  },
  /** 清空教室课表 */
  async clearClassroomSchedule() {
    const r = await classroomApi.clearSchedule()
    await store.refresh()
    return r
  },

  /** 教室使用信息 Excel 导入（防重复录入） */
  async importClassroomUsageExcel(file) {
    const result = await classroomApi.importUsageExcel(file)
    await store.refresh()
    return result
  },

  /** 某教室指定时段使用详情（点击格子弹窗） */
  roomUsageAt(building, roomNo, day, hour, week) {
    return classroomApi.usageAt(building, roomNo, day, hour, week)
  },

  /* ───────────── ⑭ PDF 教室课表 ───────────── */
  async uploadPdfSchedules(files) {
    store.pdfSchedule.uploading = true
    try {
      const result = await pdfScheduleApi.upload(files)
      await store.loadPdfSchedule()
      return result
    } finally {
      store.pdfSchedule.uploading = false
    }
  },

  async loadPdfSchedule(params = {}) {
    store.pdfSchedule.loading = true
    try {
      const [uploads, entries, options] = await Promise.all([
        pdfScheduleApi.uploads(),
        pdfScheduleApi.entries(params),
        pdfScheduleApi.options(),
      ])
      store.pdfSchedule.uploads = uploads.items || []
      store.pdfSchedule.entries = entries.items || []
      store.pdfSchedule.currentWeek = entries.current_week || null
      store.pdfSchedule.options = {
        rooms: options.rooms || [], courses: options.courses || [],
        teachers: options.teachers || [], course_types: options.course_types || [],
      }
    } finally {
      store.pdfSchedule.loading = false
    }
  },

  async removePdfSchedule(id) {
    await pdfScheduleApi.remove(id)
    await store.loadPdfSchedule()
  },
})

/* ───────────────── 组合函数（接口返回 → 视图结构）───────────────── */
function applyAccent(color) {
  document.documentElement.style.setProperty('--accent', color || '#4ade80')
}

/** 壁纸 dataURL 仅存本机（体积大，不写账号配置） */
const WALLPAPER_KEY = 'pl_wallpaper'

/**
 * 应用背景外观到 CSS 变量。
 * 说明：壁纸 + 压暗遮罩合成为一条 background-image，保证遮罩只作用于壁纸而压不到光晕。
 */
function applyAppearance() {
  const a = store.settings.appearance
  const preset = store.settings.bgPresets.find((p) => p.key === a.preset) || store.settings.bgPresets[0]
  const root = document.documentElement.style

  root.setProperty('--glow-1', preset.glow[0])
  root.setProperty('--glow-2', preset.glow[1])
  root.setProperty('--glow-3', preset.glow[2])
  root.setProperty('--glow-opacity', String(Math.max(0, (a.glow ?? 100) / 100)))
  root.setProperty('--bg', a.bgColor || '#070a08')
  root.setProperty('--grid-opacity', String(Math.max(0, (a.grid ?? 0) / 100)))
  root.setProperty('--radius', `${a.radius ?? 18}px`)

  // 壁纸：有则合成「压暗遮罩 + 图片」，无则置 none
  if (a.wallpaper) {
    const dim = Math.min(90, Math.max(0, a.wallpaperDim ?? 45)) / 100
    root.setProperty('--wp-image',
      `linear-gradient(rgba(0,0,0,${dim}), rgba(0,0,0,${dim})), url("${a.wallpaper}")`)
  } else {
    root.setProperty('--wp-image', 'none')
  }
}

/** 读取本机壁纸并合入 appearance（启动时调用） */
function loadLocalWallpaper() {
  try {
    const wp = localStorage.getItem(WALLPAPER_KEY)
    if (wp) store.settings.appearance.wallpaper = wp
  } catch { /* 隐私模式等忽略 */ }
}

function composeIdentity(me, runtime) {
  if (me) {
    store.userRaw = me
    const config = me.config || {}
    store.profile = {
      name: me.nickname || me.username,
      school: config.school || '—',
      role: config.role || '—',
      avatar: me.avatar || (me.nickname || '北').slice(0, 1),
    }
    store.settings.accent = config.accent || store.settings.accent
    store.settings.weatherCity = config.weather_city || store.settings.weatherCity
    // 背景外观：账号配置优先，缺失字段保留默认
    if (config.appearance && typeof config.appearance === 'object') {
      store.settings.appearance = { ...store.settings.appearance, ...config.appearance }
    }
  }
  if (runtime) {
    store.runtime = runtime
    store.settings.version = `v${runtime.app?.version || '1.0.0'} · Polaris Terminal`
    store.settings.backendUrl = runtime.database?.url || '—'
    store.settings.dataSource = `真实接口 · ${runtime.database?.engine || 'db'} · 缓存 ${
      runtime.cache?.mode || '-'} · AI ${runtime.ai?.mode || '-'}`
  }
}

function composeWeather(me) {
  const city = (me?.config || {}).weather_city || store.settings.weatherCity || FALLBACK_WEATHER.city
  store.weather = { ...FALLBACK_WEATHER, city }
}

function composeCourses(summary) {
  const classes = summary?.courses_today || []
  store.todayCourses = classes.map((c, i) => ({
    time: `${c.start_time} - ${c.end_time}`,
    name: c.name,
    room: c.location || '地点待定',
    teacher: c.teacher || '—',
    status: c.status === 'done' ? 'done' : c.status === 'current' ? 'current' : 'next',
    color: c.color || PALETTE[i % PALETTE.length],
  }))
}

function hourOf(hhmm) {
  return parseInt((hhmm || '08:00').slice(0, 2), 10)
}
function ceilHour(hhmm) {
  const [h, m] = (hhmm || '09:40').split(':').map(Number)
  return m > 0 ? h + 1 : h
}
function minOf(hhmm) {
  const [h, m] = (hhmm || '08:00').split(':').map(Number)
  return h * 60 + m
}

function composeTimetable(week) {
  if (!week) return
  const days = week.days || []
  const slots = []
  days.forEach((day) => {
    ;(day.classes || []).forEach((c) => {
      slots.push({
        id: c.course_id,
        day: day.weekday,
        start: hourOf(c.start_time),
        end: ceilHour(c.end_time),
        startMin: minOf(c.start_time),
        endMin: minOf(c.end_time),
        startHm: c.start_time,
        endHm: c.end_time,
        name: c.name,
        room: c.location || '待定',
        color: c.color || PALETTE[slots.length % PALETTE.length],
        weeks: c.weeks || '—',
      })
    })
  })
  store.weekTimetable = {
    hours: Array.from({ length: 14 }, (_, i) => 8 + i),
    days: WEEK_CN.map((d) => `周${d}`),
    slots,
    week: week.week || 1,
    totalClasses: slots.length,
  }
}

function composeTasks(summary, taskList, taskStats) {
  const items = taskList?.items || []
  store.notes = items.map((t) => ({
    id: t.id,
    title: t.title,
    priority: t.priority,
    category: t.category,
    due: t.due_at,
    status: t.status,
    description: t.description || '',
    estimate_minutes: t.estimate_minutes || 0,
    subtaskDone: t.subtask_done,
    subtaskTotal: t.subtask_total,
    subtasks: (t.subtasks || []).map((s) => ({ id: s.id, title: s.title, is_done: !!s.is_done })),
  }))

  const dueToday = (summary?.today_due || []).map((t) => ({
    id: t.id,
    title: t.title,
    priority: t.priority,
    due: t.due_at,
    tag: t.category,
    status: t.status,
  }))
  // 若今天没有到期任务，退化为「最近 5 项待推进」，避免卡片空白
  store.todayDdls = dueToday.length
    ? dueToday
    : items.filter((t) => t.status === 'pending').slice(0, 5).map((t) => ({
        id: t.id, title: t.title, priority: t.priority, due: t.due_at,
        tag: t.category, status: t.status,
      }))

  const stats = taskStats || summary?.tasks || {}
  const trend = stats.trend || []
  store.noteStats = {
    pending: stats.pending ?? 0,
    todayDue: stats.due_today ?? 0,
    weekDone: trend.reduce((sum, d) => sum + (d.done || 0), 0),
    overdue: stats.overdue ?? 0,
    doneTrend: {
      days: trend.map((d) => (d.date || '').slice(5)),
      done: trend.map((d) => d.done || 0),
      created: trend.map((d) => d.created || 0),
    },
    category: (stats.by_category || []).map((c) => ({ name: c.category, value: c.count })),
  }
  store.taskStats = stats
}

function composeStudy(summary, taskStats, study14, plans) {
  const daily = (study14?.daily || summary?.study?.daily || []).slice(-14)
  const last7 = daily.slice(-7)
  const prev7 = daily.slice(0, Math.max(0, daily.length - 7))
  const weekTotal = last7.reduce((s, d) => s + (d.hours || 0), 0)
  const prevTotal = prev7.reduce((s, d) => s + (d.hours || 0), 0)
  const delta = prevTotal > 0 ? ((weekTotal - prevTotal) / prevTotal) * 100 : null

  const stats = taskStats || summary?.tasks || {}
  const kaoyan = summary?.kaoyan || {}

  store.studyOverview = {
    weekDays: last7.map((d) => `周${WEEK_CN[(d.weekday || 1) - 1]}`),
    hours: last7.map((d) => Number((d.hours || 0).toFixed(1))),
    weekTotal: Number(weekTotal.toFixed(1)),
    weekDelta: delta === null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%`,
    ddlDone: stats.done ?? 0,
    ddlTotal: stats.total ?? 0,
    ddlRate: Number(((stats.completion_rate ?? 0) * 100).toFixed(1)),
    kaoyanProgress: Number((kaoyan.progress ?? 0).toFixed(1)),
    kaoyanTargetScore: kaoyan.total_target ?? 0,
    kaoyanCurrentScore: kaoyan.total_current ?? 0,
    activeDays: study14?.active_days ?? 0,
    streakDays: study14?.streak_days ?? summary?.study?.streak_days ?? 0,
    bySubject: study14?.by_subject || summary?.study?.by_subject || [],
  }
}

function composeKaoyan(summary, plans, planTasks) {
  const k = summary?.kaoyan || {}
  const phases = plans?.phases || []
  const tasks = planTasks?.items || []

  // 阶段配色：进行中的阶段用强调色
  const activeIndex = phases.findIndex((p) => (p.progress ?? 0) > 0 && (p.progress ?? 0) < 100)

  store.kaoyan = {
    hasTarget: !!k.has_target,
    school: k.school || '—',
    major: k.major || '—',
    degreeType: k.degree_type || '学硕',
    examDate: k.exam_date || null,          // 可能为 null：视图需做空值保护
    daysLeft: k.days_left ?? null,
    totalTarget: k.total_target ?? 0,
    totalCurrent: k.total_current ?? 0,
    totalGap: k.total_gap ?? 0,
    progress: Number((k.progress ?? 0).toFixed(1)),
    phaseProgress: Number((k.phase_progress ?? 0).toFixed(1)),
    focusSubjects: k.focus_subjects || [],
    subjects: (k.subjects || []).map((s) => ({
      name: s.subject,
      current: s.current,
      target: s.target,
      max: s.max,
      line: s.line,
      gap: s.gap,
      rate: Math.round((s.reach_rate ?? 0) * 100),
    })),
    phases: phases.map((p, i) => ({
      id: p.id,
      name: p.name,
      range: `${p.start_date || '—'} ~ ${p.end_date || '—'}`,
      done: p.progress ?? 0,
      focus: p.focus || '',
      color: PALETTE[i % PALETTE.length],
      current: i === activeIndex,
    })),
    dailyTasks: tasks.map((t) => ({
      id: t.id,
      done: !!t.is_done,
      text: t.title,
      minutes: t.minutes,
      subject: t.subject,
    })),
    weeklyReview: k.has_target
      ? `目标 ${k.school || ''} ${k.major || ''}：当前预估 ${k.total_current ?? 0} 分 / 目标 ${
          k.total_target ?? 0} 分，总分差 ${k.total_gap ?? 0} 分。优先补强：${
          (k.focus_subjects || []).join('、') || '待评估'}。距初试 ${k.days_left ?? '—'} 天。`
      : '尚未录入考研目标：可在下方表单填写院校、专业、初试日期与各科目标分，系统会自动计算差距与阶段计划。',
  }
}

function composeMilestones(summary, plans) {
  const list = []
  const kaoyan = summary?.kaoyan || {}
  if (kaoyan.has_target && kaoyan.exam_date) {
    list.push({
      name: '考研初试',
      date: `${kaoyan.exam_date}T08:30:00`,
      type: '考试',
      tone: 'red',
      note: `${kaoyan.school || ''} ${kaoyan.major || ''}`.trim(),
    })
  }
  const phases = plans?.phases || kaoyan.phases || []
  phases.forEach((p, i) => {
    if (!p.end_date) return
    list.push({
      name: `${p.name}结束`,
      date: `${p.end_date}T23:59:00`,
      type: '阶段',
      tone: i === 0 ? 'yellow' : 'blue',
      note: (p.focus || '').slice(0, 24),
    })
  })
  ;(summary?.upcoming_tasks || []).slice(0, 3).forEach((t) => {
    list.push({
      name: t.title,
      date: t.due_at,
      type: '截止',
      tone: t.priority === 'high' ? 'red' : 'yellow',
      note: t.category,
    })
  })
  store.milestones = list
}

function composeKnowledge(kbStats, docs, folders) {
  const stats = kbStats || {}
  const growth = (stats.growth30 || []).slice(-7).map((g) => g.count || 0)
  store.knowledgeStats = {
    docCount: stats.doc_count ?? 0,
    // 用「索引覆盖率」作为掌握度的量化代理指标（真实掌握度需人工评分）
    mastery: Number(((stats.coverage ?? 0) * 100).toFixed(1)),
    newThisWeek: stats.new_this_week ?? 0,
    wordTotal: stats.total_words ?? 0,
    weekNewTrend: growth,
    hotTags: (stats.hot_tags || []).map((t) => t.tag),
    ragCount: stats.qa_references_total ?? 0,
    chunkCount: stats.chunk_count ?? 0,
    coverage: Number(((stats.coverage ?? 0) * 100).toFixed(1)),
    vectorPending: stats.vector_pending ?? 0,
  }
  store.foldersRaw = folders?.items || []
  store.folders = (folders?.items || []).map((f) => ({ label: f.name, value: f.id }))
  composeKnowledgeDocs(docs)
}

function composeKnowledgeDocs(docs) {
  store.knowledgeDocs = (docs?.items || []).map((d) => ({
    id: d.id,
    title: d.title,
    folderId: d.folder_id ?? null,
    docType: d.doc_type || 'markdown',
    cat: (d.tags || [])[0] || '未分类',
    words: d.word_count || 0,
    updated: (d.updated_at || '').slice(5, 16),
    refs: d.read_count || 0,
    vectorStatus: d.vector_status,
    mastery: d.vector_status === 'done' ? Math.min(100, 70 + (d.read_count || 0)) : 45,
    tags: d.tags || [],
  }))
}

function composeClassroom(buildings, recent) {
  const list = buildings?.items || []
  store.classroom.overview = list
  store.classroom.room = list[0] ? { building: list[0].building, room_no: list[0].rooms?.[0] } : null
  const predict = store.classroom.predict || []
  store.classroom.records = (recent?.items || []).map((r) => ({
    id: r.id,
    time: (r.recorded_at || '').slice(5, 16),
    room: r.name,
    state: r.status_label,
    source: { miniapp: '小程序拍照', manual: '手动标记', ai_vision: 'AI 识图', web: 'Web 上报', ai: 'AI 助手' }[r.source] || r.source,
    note: r.note || '',
    photo: !!r.photo_url,
    photoUrl: r.photo_url || null,
    confidence: r.confidence,
  }))
  return { list, predict }
}

async function composeClassroomMatrix(buildings) {
  const list = buildings?.items || []
  // 优先用用户选择的教室，否则取第一个有采集记录的教室
  let sel = store.classroom.heatSel
  const valid = (b, r) => list.some((x) => x.building === b && (x.rooms || []).includes(r))
  if (!sel || !valid(sel.building, sel.room_no)) {
    // 优先选有采集记录的教室（热力图非空），否则取第一个教室
    const recorded = new Set((store.classroom.records || []).map((x) => x.room))
    sel = null
    for (const b of list) {
      const hit = (b.rooms || []).find((r) => recorded.has(`${b.building} ${r}`))
      if (hit) { sel = { building: b.building, room_no: hit }; break }
    }
    if (!sel) {
      const first = list.find((b) => b.rooms?.length)
      sel = first ? { building: first.building, room_no: first.rooms[0] } : null
    }
    store.classroom.heatSel = sel
  }
  if (!sel) return
  try {
    const [rate, predict] = await Promise.all([
      classroomApi.freeRate(sel.building, sel.room_no),
      classroomApi.predict(undefined, undefined, 5),
    ])
    store.classroom.matrix = {
      hours: rate.hours || [],
      days: WEEK_CN.map((d) => `周${d}`),
      cells: (rate.matrix || []).map((row) => row.map((cell) => (cell.rate === null ? -1 : cell.rate))),
    }
    store.classroom.matrixRoom = rate.name
    store.classroom.samples = rate.samples
    store.classroom.predict = (predict.results || []).map((r) => ({
      room: r.name,
      free: r.confidence,
      samples: r.samples,
      last: `${r.last_status === 'free' ? '空闲' : '占用'} · ${(r.last_recorded_at || '').slice(5, 16)}`,
      trend: r.confidence > 70 ? 'up' : 'flat',
    }))
    // 无样本时后端会给出原因（如"该时段暂无历史快照"），前端据此渲染空状态
    store.classroom.predictHint = predict.hint || ''
  } catch {
    store.classroom.predict = []
    store.classroom.predictHint = ''
    /* 无采集数据时保持空矩阵 */
  }
}

function composeFinance(summaryData, trendData, budgets, records) {
  const s = summaryData || {}
  const t = trendData?.items || []
  store.finance = {
    month: s.month || '',
    trendRaw: t,
    income: s.income ?? 0,
    expense: s.expense ?? 0,
    studyExpense: s.study_expense ?? 0,
    studyRatio: Number(((s.study_ratio ?? 0) * 100).toFixed(1)),
    balance: s.balance ?? 0,
    categories: (s.categories || []).map((c) => ({ name: c.category, value: c.amount })),
    trend: {
      months: t.map((x) => `${x.month.slice(5)}月`),
      expense: t.map((x) => x.expense),
      study: t.map((x) => x.study_expense),
      income: t.map((x) => x.income),
    },
    budgets: (budgets?.items || []).map((b) => ({
      id: b.id, name: b.category_label, limit: b.limit_amount, used: b.used,
      rate: Number(((b.usage_rate ?? 0) * 100).toFixed(0)), remaining: b.remaining,
    })),
    records: (records?.items || []).map((r) => ({
      id: r.id,
      date: (r.date || '').slice(5),
      dateFull: r.date || '',
      categoryRaw: r.category,
      type: r.type,
      amountRaw: r.amount,
      payment: r.payment_method,
      cat: r.category,
      item: r.note || r.category,
      amount: r.type === 'income' ? r.amount : -r.amount,
      study: r.is_study,
    })),
  }
}

function composeHealth(report, settings, records, study14) {
  const r = report || {}
  const sedentary = r.sedentary || {}
  const items = (records?.items || []).slice().sort((a, b) => (a.date < b.date ? -1 : 1))
  const today = items[items.length - 1] || null
  const todayStr = new Date().toISOString().slice(0, 10)
  const todayRecord = items.find((x) => x.date === todayStr) || null

  store.health = {
    sedentary: {
      minutes: sedentary.minutes_since_break ?? 0,
      interval: sedentary.interval_min ?? settings?.sedentary_interval_min ?? 45,
      shouldBreak: !!sedentary.should_break,
      todayBreaks: store.health?.sedentary?.todayBreaks ?? 0,
      quiet: `${settings?.quiet_start || '12:00'}-${settings?.quiet_end || '14:00'}`,
      message: sedentary.message || '',
    },
    sedentaryEnabled: settings?.sedentary_enabled ?? store.health?.sedentaryEnabled ?? true,
    lastSleep: today
      ? { hours: today.sleep_hours, bed: today.bed_time || '—', up: today.wake_time || '—', quality: today.mood ? '良好' : '—' }
      : { hours: 0, bed: '—', up: '—', quality: '—' },
    weekSleep: {
      days: items.map((x) => (x.date || '').slice(5)),
      hours: items.map((x) => x.sleep_hours || 0),
    },
    waterToday: todayRecord?.water_ml ?? 0,
    waterTarget: settings?.target_water_ml ?? 2000,
    exerciseWeek: items.map((x) => x.exercise_minutes || 0),
    checkinStreak: study14?.streak_days ?? 0,
    tips: r.tips || [],
    logs: items.slice(-8).reverse().map((x) => ({
      id: x.id,
      date: x.date,
      time: (x.date || '').slice(5),
      kind: '日报',
      value: `睡 ${x.sleep_hours}h / 动 ${x.exercise_minutes}m`,
      note: x.note || `${x.water_ml || 0}ml 饮水`,
      sleep_hours: x.sleep_hours,
      exercise_minutes: x.exercise_minutes,
      water_ml: x.water_ml,
      weight: x.weight,
      steps: x.steps,
      mood: x.mood,
      bed_time: x.bed_time,
      wake_time: x.wake_time,
    })),
  }
}

function composeAiAndStatus(summary, taskList, runtime, wxStatus, wxQuota, wxLogs, aiStatus) {
  store.runtime = runtime || store.runtime
  store.aiStatus = aiStatus
  store.wx = {
    status: wxStatus,
    quota: wxQuota,
    logs: wxLogs?.items || [],
  }

  const status = []
  status.push({ label: runtime?.database?.ok === false ? '数据库异常' : '数据同步正常', tone: runtime?.database?.ok === false ? 'red' : 'green' })
  status.push({
    label: aiStatus?.ai?.mode === 'live' ? 'AI 已就绪' : 'AI 演示模式',
    tone: aiStatus?.ai?.mode === 'live' ? 'green' : 'yellow',
  })
  const overdue = summary?.tasks?.overdue ?? 0
  status.push({
    label: overdue ? `${overdue} 项逾期` : '无逾期任务',
    tone: overdue ? 'red' : 'green',
  })
  if (wxQuota) {
    status.push({
      label: `提醒额度 ${wxQuota.total_remaining ?? 0}`,
      tone: (wxQuota.total_remaining ?? 0) > 0 ? 'green' : 'gray',
    })
  }
  if (store.errors.length) {
    status.push({ label: `${store.errors.length} 项加载失败`, tone: 'red' })
  }
  store.systemStatus = status

  // 快讯流：真实事件聚合（提醒 + 教室采集 + 推送日志 + 学习/知识库提示）
  const feed = []
  ;(summary?.alerts || []).forEach((a) => {
    feed.push({ time: '刚刚', tone: a.tone || 'blue', tag: a.tag || '系统', text: a.text })
  })
  ;(wxLogs?.items || []).slice(0, 3).forEach((logItem) => {
    feed.push({
      time: (logItem.created_at || '').slice(5, 16),
      tone: logItem.status === 'success' ? 'green' : 'yellow',
      tag: '提醒',
      text: `${logItem.kind === 'ddl' ? 'DDL' : '上课'}推送：${
        { success: '已发送', skipped_no_quota: '额度不足已跳过', skipped_duplicate: '已去重跳过',
          skipped_no_openid: '未绑定微信', skipped_not_configured: '未配置模板', failed: '发送失败' }[logItem.status]
        || logItem.status}`,
    })
  })
  if (runtime) {
    feed.push({
      time: '系统',
      tone: 'blue',
      tag: '运行态',
      text: `数据库 ${runtime.database?.engine} · 缓存 ${runtime.cache?.mode} · AI ${runtime.ai?.mode}`,
    })
  }
  if (summary?.knowledge?.doc_count !== undefined) {
    feed.push({
      time: '今日',
      tone: 'green',
      tag: '知识库',
      text: `共 ${summary.knowledge.doc_count} 篇文档 / ${summary.knowledge.chunk_count} 个检索切片`,
    })
  }
  const pendingCount = taskList?.items?.filter((t) => t.status === 'pending').length ?? 0
  feed.push({
    time: '任务',
    tone: pendingCount > 5 ? 'yellow' : 'green',
    tag: 'DDL',
    text: `当前待推进 ${pendingCount} 项`,
  })
  store.newsFeed = feed.length ? feed : [{ time: '刚刚', tone: 'green', tag: '系统', text: '暂无动态，一切正常 ✦' }]

  // 教室采集快讯由 composeClassroom 之后补充
  setTimeout(() => {
    if (!store.classroom.records.length) return
    const latest = store.classroom.records[0]
    const exists = store.newsFeed.some((n) => n.text.includes(latest.room))
    if (!exists) {
      store.newsFeed.splice(1, 0, {
        time: latest.time,
        tone: latest.state === '空闲' ? 'green' : 'yellow',
        tag: '教室',
        text: `${latest.room} ${latest.state}（${latest.source}）`,
      })
    }
  }, 0)
}

/* 启动即应用背景外观（含本机壁纸），登录页也能看到自定义效果 */
loadLocalWallpaper()
applyAppearance()
