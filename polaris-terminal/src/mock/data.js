/**
 * 北极星 · 个人战略终端 —— 静态原型全量 mock 数据
 * （后续接真实后端时，仅需把 store/index.js 的初始化替换为 API 拉取）
 */

const DAY_MS = 86400000
export function futureDate(days, hour = 23, min = 59) {
  const d = new Date(Date.now() + days * DAY_MS)
  d.setHours(hour, min, 0, 0)
  return d
}
const iso = (d) => {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`
}

/* ── 用户与状态栏 ── */
export const profile = {
  name: '北极星同学',
  school: '华中科技大学',
  role: '23 级计算机 · 考研备战中',
  avatar: '北',
}

export const systemStatus = [
  { label: '数据同步正常', tone: 'green' },
  { label: 'AI 引擎就绪', tone: 'green' },
  { label: '3 个 DDL 临近', tone: 'yellow' },
]

export const weather = { city: '武汉', text: '多云', icon: '⛅', temp: 22, range: '18~25℃', aqi: '良 46' }

/* ── 总览 · 今日课程 ── */
export const todayCourses = [
  { time: '08:00 - 09:40', name: '数据结构与算法', room: '东一舍 A302', teacher: '王教授', status: 'done', color: '#60a5fa' },
  { time: '10:00 - 11:40', name: '毛泽东思想概论', room: '主楼 201', teacher: '李老师', status: 'done', color: '#c084fc' },
  { time: '14:00 - 15:40', name: '操作系统原理', room: '东一舍 A305', teacher: '张教授', status: 'current', color: '#4ade80' },
  { time: '16:00 - 17:40', name: '计算机网络实验', room: '网楼 B203', teacher: '陈老师', status: 'next', color: '#facc15' },
  { time: '19:00 - 21:00', name: '408 晚自习刷题', room: '图书馆 4F 自习区', teacher: '自主', status: 'next', color: '#f87171' },
]

/* ── 总览 · 今日待推进 DDL（按优先级） ── */
export const todayDdls = [
  { id: 1, title: '操作系统进程调度实验报告', priority: 'high', due: iso(futureDate(0, 22)), tag: '课程', status: 'pending' },
  { id: 2, title: '数学模拟卷（三）订正归档', priority: 'high', due: iso(futureDate(0, 23, 30)), tag: '考研', status: 'pending' },
  { id: 3, title: '计算机网络实验预习笔记上传知识库', priority: 'medium', due: iso(futureDate(0, 21)), tag: '知识整理', status: 'pending' },
  { id: 4, title: '明日线性代数作业（提前）', priority: 'low', due: iso(futureDate(1, 8)), tag: '课程', status: 'pending' },
]

/* ── 总览 · 重要节点 ── */
export const milestones = [
  { name: '考研初试', date: iso(futureDate(95, 8, 30)), type: '考试', tone: 'red', note: '华科计算机学院 · 408' },
  { name: '研究生报名确认', date: iso(futureDate(11, 22)), type: '截止', tone: 'yellow', note: '学信网网上确认' },
  { name: '英语六级考试', date: iso(futureDate(38, 9)), type: '考试', tone: 'yellow', note: '目标 550+' },
  { name: '数据结构课程结课', date: iso(futureDate(17, 10)), type: '节点', tone: 'blue', note: '结课大作业答辩' },
  { name: '11 月学习预算复盘', date: iso(futureDate(25, 20)), type: '财务', tone: 'blue', note: '投入产出分析' },
]

/* ── 总览 · 学习数据概览 ── */
export const studyOverview = {
  weekDays: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  hours: [7.5, 8.2, 6.4, 9.1, 7.8, 10.5, 6.2],
  weekTotal: 55.7,
  weekDelta: '+8.4%',
  ddlDone: 17,
  ddlTotal: 22,
  ddlRate: 77.3,
  kaoyanProgress: 64.5,
  kaoyanTargetScore: 420,
  kaoyanCurrentScore: 289,
}

/* ── 总览 · 知识库量化 ── */
export const knowledgeStats = {
  docCount: 48,
  mastery: 82.4,
  newThisWeek: 6,
  wordTotal: 128600,
  weekNewTrend: [2, 3, 1, 4, 2, 5, 6],
  hotTags: ['408-操作系统', '数学强化', '英语长难句', '复试项目', '专业课真题', '错题本'],
  ragCount: 143,
}

/* ── 总览 · 快讯头条 ── */
export const newsFeed = [
  { time: '2 分钟前', tone: 'yellow', tag: '健康', text: '已连续久坐 52 分钟，建议起身活动 5 分钟' },
  { time: '18 分钟前', tone: 'green', tag: '小程序', text: '采集快照：东一舍 A305 当前空闲（附 1 张照片）' },
  { time: '36 分钟前', tone: 'red', tag: 'DDL', text: '「操作系统实验报告」今晚 22:00 截止，剩余 3 小时' },
  { time: '1 小时前', tone: 'blue', tag: 'AI', text: '周复盘已生成：本周学习 55.7h，较上周 +8.4%' },
  { time: '3 小时前', tone: 'green', tag: '财务', text: '「书籍」类目预算使用 76%，剩余 ¥118' },
  { time: '今早 07:55', tone: 'blue', tag: '课表', text: '今日 5 节课，第一节 08:00 东一舍 A302' },
  { time: '昨天', tone: 'green', tag: '知识库', text: '新增文档《进程调度算法对比笔记》，已进入 RAG 索引' },
]

/* ── 课程表 · 周课表 ── */
export const weekTimetable = {
  hours: [8, 10, 12, 14, 16, 18, 20],
  days: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  slots: [
    { day: 1, start: 8, end: 10, name: '数据结构与算法', room: '东一A302', color: '#60a5fa', weeks: '1-16周' },
    { day: 1, start: 14, end: 16, name: '形势与政策', room: '主楼101', color: '#c084fc', weeks: '单周' },
    { day: 1, start: 19, end: 21, name: '408晚自习', room: '图书馆4F', color: '#4ade80', weeks: '全程' },
    { day: 2, start: 10, end: 12, name: '毛概', room: '主楼201', color: '#c084fc', weeks: '1-12周' },
    { day: 2, start: 14, end: 16, name: '线性代数', room: '东二401', color: '#facc15', weeks: '1-16周' },
    { day: 3, start: 8, end: 10, name: '操作系统原理', room: '东一A305', color: '#4ade80', weeks: '2-17周' },
    { day: 3, start: 16, end: 18, name: '网络实验', room: '网楼B203', color: '#f87171', weeks: '双周' },
    { day: 4, start: 10, end: 12, name: '线性代数', room: '东二401', color: '#facc15', weeks: '1-16周' },
    { day: 4, start: 14, end: 16, name: '数据结构习题课', room: '东一A302', color: '#60a5fa', weeks: '5-15周' },
    { day: 5, start: 8, end: 10, name: '操作系统原理', room: '东一A305', color: '#4ade80', weeks: '2-17周' },
    { day: 5, start: 10, end: 12, name: '大学英语(考研方向)', room: '外楼305', color: '#60a5fa', weeks: '1-16周' },
    { day: 6, start: 9, end: 12, name: '数学强化班', room: '线上直播', color: '#facc15', weeks: '全程' },
    { day: 7, start: 14, end: 17, name: '专业课项目实践', room: '网楼B501', color: '#4ade80', weeks: '全程' },
  ],
}

/* ── 事项备忘 · 全量任务 ── */
export const notes = [
  { id: 11, title: '操作系统进程调度实验报告', priority: 'high', category: '课程', due: iso(futureDate(0, 22)), status: 'pending' },
  { id: 12, title: '数学模拟卷（三）订正归档', priority: 'high', category: '考研', due: iso(futureDate(0, 23, 30)), status: 'pending' },
  { id: 13, title: '计算机网络实验预习笔记上传知识库', priority: 'medium', category: '知识整理', due: iso(futureDate(0, 21)), status: 'pending' },
  { id: 14, title: '考研报名网上确认材料准备', priority: 'high', category: '考研', due: iso(futureDate(11, 22)), status: 'pending' },
  { id: 15, title: '数据结构结课大作业开题', priority: 'medium', category: '课程', due: iso(futureDate(14, 18)), status: 'pending' },
  { id: 16, title: '六级单词冲刺计划第 3 阶段', priority: 'medium', category: '考研', due: iso(futureDate(30)), status: 'pending' },
  { id: 17, title: '缴纳网球场会员卡续费', priority: 'low', category: '生活', due: iso(futureDate(5, 20)), status: 'pending' },
  { id: 18, title: '整理 10 月错题本电子档', priority: 'medium', category: '知识整理', due: iso(futureDate(-1, 22)), status: 'pending' },
  { id: 19, title: '提交综测加分材料', priority: 'low', category: '生活', due: iso(futureDate(8, 12)), status: 'done' },
  { id: 20, title: '图书馆书籍归还', priority: 'medium', category: '生活', due: iso(futureDate(-3)), status: 'done' },
]

export const noteStats = {
  pending: notes.filter((n) => n.status === 'pending').length,
  todayDue: 3,
  weekDone: 12,
  overdue: 1,
  category: [
    { name: '考研', value: 38 }, { name: '课程', value: 27 }, { name: '知识整理', value: 21 }, { name: '生活', value: 14 },
  ],
  doneTrend: { days: ['10-08', '10-09', '10-10', '10-11', '10-12', '10-13', '10-14'], done: [4, 6, 3, 5, 7, 2, 6], created: [5, 5, 4, 6, 6, 3, 7] },
}

/* ── 空教室 · 热力 / 预测 / 采集记录 ── */
export const classroomFreeMatrix = {
  hours: [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
  days: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  // 每格：空闲率 0~1（-1 表示无数据）
  cells: [
    [0.2, 0.1, 0.1, 0.2, 0.9, 0.9, 0.3, 0.2, 0.4, 0.5, 0.9, 0.7, 0.5, 0.6],
    [0.3, 0.5, 0.2, 0.4, 0.9, 0.8, 0.5, 0.3, 0.2, 0.6, 0.7, 0.8, 0.6, 0.7],
    [0.1, 0.4, 0.6, 0.3, 0.8, 0.9, 0.2, 0.5, 0.7, 0.4, 0.6, 0.9, 0.8, 0.8],
    [0.4, 0.2, 0.5, 0.7, 0.9, 0.7, 0.3, 0.1, 0.6, 0.5, 0.8, 0.6, 0.7, 0.6],
    [0.2, 0.6, 0.3, 0.2, 0.7, 0.8, 0.5, 0.6, 0.4, 0.3, 0.7, 0.5, 0.3, 0.5],
    [0.8, 0.8, 0.9, 0.9, 0.9, 0.8, 0.7, 0.7, 0.6, 0.6, 0.5, 0.4, 0.3, 0.2],
    [0.7, 0.9, 0.9, 0.8, 0.8, 0.7, 0.6, 0.5, 0.5, 0.4, 0.3, 0.2, 0.2, 0.1],
  ],
}

export const classroomPredict = [
  { room: '东一舍 A305', free: 88, samples: 42, last: '空闲 · 10 分钟前(小程序采集)', trend: 'up' },
  { room: '图书馆 4F 北区', free: 74, samples: 35, last: '空闲 · 25 分钟前', trend: 'up' },
  { room: '网楼 B101 开放自习', free: 71, samples: 28, last: '占用 · 2 小时前', trend: 'flat' },
  { room: '西五舍 研讨间 2', free: 63, samples: 15, last: '空闲 · 1 小时前', trend: 'down' },
]

export const classroomRecords = [
  { time: '今天 14:22', room: '东一舍 A305', state: '空闲', source: '小程序拍照', note: '约剩 40% 座位', photo: true },
  { time: '今天 13:58', room: '图书馆 4F 北区', state: '空闲', source: '小程序拍照', note: '靠窗有位', photo: true },
  { time: '今天 11:47', room: '网楼 B101', state: '占用', source: '小程序拍照', note: '被研讨课预占', photo: true },
  { time: '昨天 20:31', room: '东一舍 A305', state: '空闲', source: '手动标记', note: '', photo: false },
  { time: '昨天 16:05', room: '西五舍 研讨间2', state: '占用', source: '小程序拍照', note: '社团活动', photo: true },
]

/* ── 考研规划 ── */
export const kaoyan = {
  school: '华中科技大学',
  major: '计算机科学与技术（学硕）',
  examDate: iso(futureDate(95, 8, 30)),
  totalTarget: 420,
  totalCurrent: 289,
  subjects: [
    { name: '政治', current: 58, target: 75, max: 100 },
    { name: '英语一', current: 62, target: 80, max: 100 },
    { name: '数学一', current: 96, target: 130, max: 150 },
    { name: '408 计算机', current: 73, target: 135, max: 150 },
  ],
  phases: [
    { name: '基础阶段', range: '3月 - 6月', done: 100, focus: '教材 + 基础题全覆盖', color: '#60a5fa' },
    { name: '强化阶段', range: '7月 - 10月中', done: 74, focus: '专题突破 + 真题一轮', color: '#4ade80', current: true },
    { name: '冲刺阶段', range: '10月中 - 考前', done: 0, focus: '模拟卷 + 查漏补缺 + 背诵', color: '#facc15' },
  ],
  dailyTasks: [
    { done: true, text: '数学：880 题 线代章节 12 题订正', minutes: 75, subject: '数学' },
    { done: true, text: '408：操作系统·进程调度 强化课 1.5h', minutes: 90, subject: '408' },
    { done: false, text: '英语：长难句精析 3 句 + 核心词 60 个', minutes: 50, subject: '英语' },
    { done: false, text: '政治：马原选择题 20 题', minutes: 40, subject: '政治' },
    { done: false, text: '错题归档入知识库（RAG 更新）', minutes: 25, subject: '整理' },
  ],
  weeklyReview: '本周有效学习 31.5h（目标 35h，达成 90%）。数学线代正确率从 68% → 76% 提升显著；408 操作系统大题步骤分仍丢 15%。建议下周把 408 真题大题拆成每日 1 题精练，政治马原保持题感。',
}

/* ── 知识整理 ── */
export const knowledgeDocs = [
  { title: '进程调度算法对比笔记', cat: '408-操作系统', words: 3200, updated: '今天 13:40', refs: 18, mastery: 92 },
  { title: '数学模拟卷三 · 错题归档', cat: '数学强化', words: 1860, updated: '今天 11:02', refs: 9, mastery: 78 },
  { title: '计算机网络·运输层要点', cat: '408-网络', words: 4100, updated: '昨天 21:15', refs: 14, mastery: 85 },
  { title: '英语一·长难句拆解 20 例', cat: '英语长难句', words: 2600, updated: '昨天 19:40', refs: 22, mastery: 88 },
  { title: '复试项目：校园助手小程序设计稿', cat: '复试项目', words: 5400, updated: '3 天前', refs: 6, mastery: 70 },
  { title: '毛概·史纲时间线速记', cat: '政治', words: 1500, updated: '4 天前', refs: 3, mastery: 66 },
]

export const ragDemo = {
  question: '时间片轮转和优先级调度有什么区别？',
  answer: '时间片轮转（RR）按固定时间片轮流执行就绪队列中的进程，强调公平性与响应时间，适合分时系统；优先级调度则按进程优先级高低分配 CPU，可抢占或非抢占，强调重要性差异，实时系统常用。二者可结合：同优先级内部采用 RR（多级反馈队列即为此思路）。[资料1·进程调度算法对比笔记]',
  refs: ['资料1 进程调度算法对比笔记', '资料2 操作系统·课后习题第3章'],
}

/* ── 资产财务 ── */
export const finance = {
  month: '2026-10',
  income: 2500,
  expense: 1836.4,
  studyExpense: 542,
  studyRatio: 29.5,
  balance: 663.6,
  categories: [
    { name: '餐饮', value: 762.4 }, { name: '学习投入', value: 542 }, { name: '交通', value: 96 },
    { name: '娱乐', value: 152 }, { name: '日用品', value: 186 }, { name: '其他', value: 98 },
  ],
  trend: {
    months: ['5月', '6月', '7月', '8月', '9月', '10月'],
    expense: [1622, 1893, 2105, 2260, 1774, 1836],
    study: [320, 410, 680, 735, 468, 542],
    income: [2450, 2500, 2500, 2800, 2500, 2500],
  },
  budgets: [
    { name: '总预算', limit: 2200, used: 1836 },
    { name: '餐饮', limit: 900, used: 762 },
    { name: '学习投入', limit: 700, used: 542 },
    { name: '娱乐', limit: 200, used: 152 },
  ],
  records: [
    { date: '10-14', cat: '学习投入', item: '考研数学强化班网课', amount: -320, study: true },
    { date: '10-13', cat: '餐饮', item: '食堂周卡', amount: -85, study: false },
    { date: '10-12', cat: '学习投入', item: '408 真题册（第二遍）', amount: -68, study: true },
    { date: '10-11', cat: '交通', item: '高铁·回家往返', amount: -108, study: false },
    { date: '10-10', cat: '收入', item: '助教岗位补贴', amount: 300, study: false },
    { date: '10-09', cat: '日用品', item: '台灯 + 计时器', amount: -96, study: false },
  ],
}

/* ── 健康管理 ── */
export const health = {
  sedentary: { minutes: 52, interval: 45, shouldBreak: true, todayBreaks: 6, quiet: '12:00-14:00 / 22:30后' },
  lastSleep: { hours: 7.2, bed: '23:48', up: '07:00', quality: '一般' },
  weekSleep: { days: ['10-08', '10-09', '10-10', '10-11', '10-12', '10-13', '10-14'], hours: [7.8, 6.9, 7.4, 6.5, 8.1, 7.6, 7.2] },
  waterToday: 1450, waterTarget: 2000,
  exerciseWeek: [40, 0, 60, 30, 0, 75, 45],
  checkinStreak: 23,
  logs: [
    { time: '07:00', kind: '起床', value: '', note: '比计划晚 20 分钟' },
    { time: '07:30', kind: '饮水', value: '500ml', note: '' },
    { time: '12:10', kind: '午休', value: '25min', note: '趴在桌' },
    { time: '13:55', kind: '起身活动', value: '5min', note: '楼梯 3 层' },
    { time: '15:30', kind: '饮水', value: '450ml', note: '' },
    { time: '18:40', kind: '运动', value: '45min', note: '慢跑 4.2km' },
  ],
}

/* ── 系统设置 ── */
export const settings = {
  accent: '#4ade80',
  accentPresets: [
    { name: '极光绿', value: '#4ade80' }, { name: '深海蓝', value: '#60a5fa' },
    { name: '赛博紫', value: '#c084fc' }, { name: '落日橙', value: '#fb923c' },
  ],
  weatherCity: '武汉',
  sidebarCollapsed: false,
  dataSource: '静态原型 Mock（未接后端）',
  backendUrl: 'http://127.0.0.1:8000（预留，接入后切换）',
  version: 'v1.0.0 · Polaris Terminal',
}
