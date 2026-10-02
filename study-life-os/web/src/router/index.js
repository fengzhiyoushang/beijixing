import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY } from '../api/http'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '总览仪表盘' } },
      { path: 'timetable', name: 'timetable', component: () => import('../views/TimetableView.vue'), meta: { title: '课程表管理' } },
      { path: 'tasks', name: 'tasks', component: () => import('../views/TasksView.vue'), meta: { title: 'DDL 任务' } },
      { path: 'classroom', name: 'classroom', component: () => import('../views/ClassroomView.vue'), meta: { title: '空教室分析' } },
      { path: 'kaoyan', name: 'kaoyan', component: () => import('../views/KaoyanView.vue'), meta: { title: '考研规划' } },
      { path: 'knowledge', name: 'knowledge', component: () => import('../views/KnowledgeView.vue'), meta: { title: '知识库' } },
      { path: 'finance', name: 'finance', component: () => import('../views/FinanceView.vue'), meta: { title: '个人财务' } },
      { path: 'health', name: 'health', component: () => import('../views/HealthView.vue'), meta: { title: '个人健康' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (!token && to.name !== 'login') return '/login'
  if (token && to.name === 'login') return '/dashboard'
  return true
})

export default router
