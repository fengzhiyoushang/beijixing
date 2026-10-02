<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { store } from '../store'

const route = useRoute()
const router = useRouter()

const menus = [
  { path: '/', title: '总览', icon: '◎' },
  { path: '/courses', title: '课程表', icon: '▤' },
  { path: '/notes', title: '事项备忘', icon: '☑' },
  { path: '/classroom', title: '空教室', icon: '▣' },
  { path: '/kaoyan', title: '发展规划', icon: '✧' },
  { path: '/knowledge', title: '知识整理', icon: '≡' },
  { path: '/ai', title: 'AI 助手', icon: '✦' },
  { path: '/finance', title: '资产财务', icon: '¥' },
  { path: '/health', title: '健康管理', icon: '♥' },
  { path: '/settings', title: '系统设置', icon: '⚙' },
]

const collapsed = computed(() => store.sidebarCollapsed)

/* 今日推进度：已完成课程占比 */
const doneRatio = computed(() => {
  const total = store.todayCourses.length || 1
  const done = store.todayCourses.filter((c) => c.status === 'done').length
  return Math.round((done / total) * 100)
})

/* 迷你日历（参考稿左下角） */
const today = new Date()
const calendar = computed(() => {
  const year = today.getFullYear()
  const month = today.getMonth()
  const first = new Date(year, month, 1)
  const startPad = (first.getDay() + 6) % 7          // 周一为一周起点
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < startPad; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)
  while (cells.length % 7 !== 0) cells.push(null)
  return { year, month: month + 1, cells }
})
const isToday = (d) => d === today.getDate()
const WEEK = ['一', '二', '三', '四', '五', '六', '日']
</script>

<template>
  <aside class="side" :class="{ collapsed }">
    <!-- 品牌区（参考稿：Logo 在侧栏顶部） -->
    <div class="brand">
      <div class="logo">
        <span class="star">✦</span>
        <span class="ring" />
      </div>
      <div v-show="!collapsed" class="brand-txt">
        <div class="name">北极星</div>
        <div class="sub">个人战略终端</div>
      </div>
    </div>

    <nav class="menu">
      <RouterLink
        v-for="m in menus"
        :key="m.path"
        :to="m.path"
        class="item"
        :class="{ active: route.path === m.path }"
        :title="m.title"
      >
        <span class="ico">{{ m.icon }}</span>
        <span v-show="!collapsed" class="txt">{{ m.title }}</span>
      </RouterLink>
    </nav>

    <div class="foot">
      <!-- 迷你日历 -->
      <div v-show="!collapsed" class="cal">
        <div class="cal-head">
          <span class="cal-month mono">{{ calendar.year }}年{{ calendar.month }}月</span>
          <button class="more" @click="router.push('/courses?view=month')">查看全部 →</button>
        </div>
        <div class="cal-week">
          <span v-for="w in WEEK" :key="w">{{ w }}</span>
        </div>
        <div class="cal-grid">
          <span
            v-for="(d, i) in calendar.cells" :key="i"
            class="cal-day" :class="{ today: d && isToday(d), dim: !d }"
          >{{ d || '' }}</span>
        </div>
      </div>

      <!-- 今日推进度 -->
      <div v-show="!collapsed" class="progress-mini">
        <div class="row"><span class="label-3">今日推进度</span><span class="mono val">{{ doneRatio }}%</span></div>
        <div class="track"><div class="fill" :style="{ width: doneRatio + '%' }" /></div>
      </div>

      <!-- 用户卡（参考稿左下角） -->
      <div class="user-card" :class="{ mini: collapsed }">
        <div class="avatar mono">{{ store.profile.avatar }}</div>
        <div v-show="!collapsed" class="u-txt">
          <div class="u-name">{{ store.profile.name }}</div>
          <div class="u-role">{{ store.profile.role }}</div>
        </div>
      </div>

      <button class="collapse-btn" :title="collapsed ? '展开导航' : '收起导航'" @click="store.toggleSidebar()">
        {{ collapsed ? '»' : '« 收起' }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.side {
  width: var(--nav-w);
  flex-shrink: 0;
  background: linear-gradient(180deg, rgba(20, 27, 24, 0.9), rgba(13, 18, 16, 0.92));
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.22s ease;
  overflow: hidden;
  position: relative;
  z-index: 2;
  backdrop-filter: blur(10px);
}
.side.collapsed { width: var(--nav-w-mini); }

/* 品牌（桌面版可作为窗口拖拽区） */
.brand { display: flex; align-items: center; gap: 10px; padding: 18px 16px 12px; -webkit-app-region: drag; }
.logo { position: relative; width: 30px; height: 30px; display: grid; place-items: center; flex-shrink: 0; }
.star { color: var(--accent); font-size: 19px; text-shadow: 0 0 16px var(--accent); }
.ring { position: absolute; inset: 0; border: 1px solid rgba(74, 222, 128, 0.35); border-radius: 50%; }
.brand-txt .name { font-size: 15px; font-weight: 700; letter-spacing: 1px; }
.brand-txt .sub { font-size: 10.5px; color: var(--text-3); letter-spacing: 0.5px; }

/* 菜单 */
.menu { padding: 6px 12px; display: flex; flex-direction: column; gap: 3px; }
.item {
  position: relative;
  display: flex; align-items: center; gap: 11px;
  height: 42px; padding: 0 13px; border-radius: 12px;
  color: var(--text-2); text-decoration: none; font-size: 14px;
  border: 1px solid transparent;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
  white-space: nowrap;
}
.item:hover { background: rgba(255, 255, 255, 0.04); color: var(--text-1); }
.item.active {
  background: linear-gradient(90deg, rgba(74, 222, 128, 0.16), rgba(74, 222, 128, 0.05));
  color: var(--accent); border-color: rgba(74, 222, 128, 0.28);
  box-shadow: inset 0 0 20px rgba(74, 222, 128, 0.06);
}
.ico { width: 18px; text-align: center; font-size: 14px; opacity: 0.9; }
.txt { font-size: 13.5px; }
.side.collapsed .item { justify-content: center; padding: 0; }

/* 底部 */
.foot { margin-top: auto; padding: 10px 12px 14px; display: flex; flex-direction: column; gap: 10px; }

.cal {
  border: 1px solid var(--border); border-radius: 14px; padding: 10px 11px 8px;
  background: rgba(255, 255, 255, 0.02);
}
.cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.cal-month { font-size: 11.5px; color: var(--text-1); }
.cal-week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; margin-bottom: 3px; }
.cal-week span { text-align: center; font-size: 9.5px; color: var(--text-3); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.cal-day {
  height: 22px; display: grid; place-items: center; font-size: 10.5px;
  color: var(--text-2); border-radius: 6px;
  font-family: "JetBrains Mono", Consolas, monospace;
}
.cal-day.dim { color: transparent; }
.cal-day.today {
  background: var(--accent); color: #06170d; font-weight: 700;
  box-shadow: 0 0 12px rgba(74, 222, 128, 0.5);
}

.progress-mini { padding: 0 2px; }
.progress-mini .row { display: flex; justify-content: space-between; align-items: center; }
.progress-mini .val { color: var(--accent); font-size: 12.5px; }
.track { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.08); margin-top: 7px; overflow: hidden; }
.fill { height: 100%; background: var(--accent); box-shadow: 0 0 8px var(--accent); transition: width 0.3s ease; }

.user-card {
  display: flex; align-items: center; gap: 10px;
  border: 1px solid var(--border); border-radius: 14px; padding: 9px 11px;
  background: rgba(255, 255, 255, 0.02);
}
.user-card.mini { justify-content: center; padding: 8px; }
.avatar {
  width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
  background: rgba(74, 222, 128, 0.14); border: 1px solid rgba(74, 222, 128, 0.4);
  color: var(--accent); font-size: 13px; flex-shrink: 0;
}
.u-name { font-size: 12.5px; color: var(--text-1); }
.u-role { font-size: 10px; color: var(--text-3); margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }

.collapse-btn {
  height: 30px; border-radius: 10px; cursor: pointer;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 11.5px;
}
.collapse-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
</style>
