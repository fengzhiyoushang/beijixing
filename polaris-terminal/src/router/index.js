import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api/http'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录', plain: true } },
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '总览', icon: '◎' } },
  { path: '/bookmarks', name: 'bookmarks', component: () => import('../views/BookmarksView.vue'), meta: { title: '地址中心', icon: '🌐' } },
  { path: '/news', name: 'news', component: () => import('../views/NewsView.vue'), meta: { title: '新闻资讯', icon: '📰' } },
  { path: '/courses', name: 'courses', component: () => import('../views/CoursesView.vue'), meta: { title: '课程表', icon: '▤' } },
  { path: '/notes', name: 'notes', component: () => import('../views/NotesView.vue'), meta: { title: '事项备忘', icon: '☑' } },
  { path: '/classroom', name: 'classroom', component: () => import('../views/ClassroomView.vue'), meta: { title: '空教室', icon: '▣' } },
  { path: '/pdf-schedule', redirect: { path: '/courses', query: { view: 'pdf' } } },
  { path: '/kaoyan', name: 'kaoyan', component: () => import('../views/KaoyanView.vue'), meta: { title: '考研规划', icon: '✧' } },
  { path: '/knowledge', name: 'knowledge', component: () => import('../views/KnowledgeView.vue'), meta: { title: '知识整理', icon: '≡' } },
  { path: '/ai', name: 'ai', component: () => import('../views/AiAssistantView.vue'), meta: { title: 'AI 助手', icon: '✦' } },
  { path: '/finance', name: 'finance', component: () => import('../views/FinanceView.vue'), meta: { title: '资产财务', icon: '¥' } },
  { path: '/health', name: 'health', component: () => import('../views/HealthView.vue'), meta: { title: '健康管理', icon: '♥' } },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: '系统设置', icon: '⚙' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：除登录页外均需 token
router.beforeEach((to) => {
  const authed = !!getToken()
  if (!authed && to.path !== '/login') return { path: '/login', query: { redirect: to.fullPath } }
  if (authed && to.path === '/login') return { path: '/' }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || ''} · 北极星个人战略终端`
})

export default router
