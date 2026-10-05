<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, NModal, NPopover, useMessage } from 'naive-ui'
import { store } from '../store'
import { authApi } from '../api'

const route = useRoute()
const router = useRouter()
const message = useMessage()

/* ── 左上角头像窗口：个人信息查看 + 自定义编辑 ── */
const showProfile = ref(false)
const showEdit = ref(false)
const saving = ref(false)
const form = ref({ nickname: '', avatar: '', school: '', role: '' })

function openEdit() {
  const u = store.userRaw || {}
  const cfg = u.config || {}
  form.value = {
    nickname: store.profile.name || '',
    avatar: (u.avatar || '').slice(0, 2),
    school: cfg.school || '',
    role: cfg.role || '',
  }
  showEdit.value = true
}

async function saveProfile() {
  if (!form.value.nickname.trim()) { message.warning('请填写昵称'); return }
  saving.value = true
  try {
    await store.updateProfile({
      nickname: form.value.nickname.trim(),
      avatar: form.value.avatar.trim() || null,
    })
    await store.updateProfileConfig({
      school: form.value.school.trim() || '—',
      role: form.value.role.trim() || '—',
    })
    message.success('个人信息已更新')
    showEdit.value = false
  } catch (err) {
    message.error(err.message)
  } finally {
    saving.value = false
  }
}

function goSettings() {
  showProfile.value = false
  router.push('/settings')
}
function logout() {
  showProfile.value = false
  store.logout()
}

const MENUS = [
  { path: '/', title: '总览', icon: '◎' },
  { path: '/bookmarks', title: '地址中心', icon: '⊕' },
  { path: '/news', title: '新闻资讯', icon: '❐' },
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

/* ── 长按拖拽排序（持久化到用户配置 config.nav_order，跨端口/重启不丢） ── */
const NAV_ORDER_KEY = 'pl_nav_order'   // 本地兜底（未登录时）
const menus = ref(orderBySaved(readSavedOrder()))

function readSavedOrder() {
  const remote = store.userRaw?.config?.nav_order
  if (Array.isArray(remote) && remote.length) return remote
  try {
    const saved = JSON.parse(localStorage.getItem(NAV_ORDER_KEY) || 'null')
    if (Array.isArray(saved) && saved.length) return saved
  } catch { /* 忽略损坏的排序数据 */ }
  return null
}

function orderBySaved(saved) {
  const list = [...MENUS]
  if (!saved) return list
  const byPath = Object.fromEntries(MENUS.map((m) => [m.path, m]))
  const ordered = saved.map((p) => byPath[p]).filter(Boolean)
  // 新增菜单项追加到末尾
  MENUS.forEach((m) => { if (!ordered.includes(m)) ordered.push(m) })
  return ordered
}

// 登录后（store.userRaw 就绪）用远端排序刷新；本次会话刚拖拽过则不覆盖
let userDragged = false
watch(() => store.userRaw?.config?.nav_order, (remote) => {
  if (userDragged || !Array.isArray(remote) || !remote.length) return
  const next = orderBySaved(remote)
  if (next.map((m) => m.path).join() !== menus.value.map((m) => m.path).join()) menus.value = next
})

const dragIdx = ref(-1)        // 正在拖拽的项（长按后 >=0）
let longPressTimer = null
let dragged = false            // 本次 pointer 序列发生过拖拽 → 抑制随后的导航点击

function clearPress() {
  if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null }
}

function onPointerDown(e, i) {
  if (e.button !== 0) return
  dragged = false
  clearPress()
  longPressTimer = setTimeout(() => {
    dragIdx.value = i
    dragged = true
    document.body.style.userSelect = 'none'
  }, 450)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp, { once: true })
}

function onPointerMove(e) {
  if (dragIdx.value < 0) {
    // 长按未达成前移动超过阈值 → 取消长按（视为普通点击/滚动）
    if (longPressTimer && (Math.abs(e.movementX) > 3 || Math.abs(e.movementY) > 3)) clearPress()
    return
  }
  const els = menuEl.value ? [...menuEl.value.querySelectorAll('.item')] : []
  let target = -1
  const y = e.clientY
  els.forEach((el, j) => {
    const r = el.getBoundingClientRect()
    if (y >= r.top && y <= r.bottom) target = j
  })
  if (target >= 0 && target !== dragIdx.value) {
    const [moved] = menus.value.splice(dragIdx.value, 1)
    menus.value.splice(target, 0, moved)
    dragIdx.value = target
  }
}

function onPointerUp() {
  clearPress()
  window.removeEventListener('pointermove', onPointerMove)
  document.body.style.userSelect = ''
  if (dragIdx.value >= 0) {
    const order = menus.value.map((m) => m.path)
    userDragged = true
    localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(order))
    // 持久化到账号配置（merge 模式），失败不影响本地体验
    authApi.updateConfig({ nav_order: order }, true).catch(() => {})
    dragIdx.value = -1
  }
}

/* 拖拽刚结束时拦截 RouterLink 跳转 */
function onNavClick(e) {
  if (dragged) { e.preventDefault(); dragged = false }
}

const menuEl = ref(null)

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
    <!-- 品牌区：点击头像打开个人信息窗口（功能已从右上角迁移至此） -->
    <NPopover trigger="click" placement="bottom-start" :show="showProfile" raw @update:show="(v) => (showProfile = v)">
      <template #trigger>
        <div class="brand" :class="{ mini: collapsed }">
          <div class="logo">
            <span class="star">{{ store.profile.avatar || '✦' }}</span>
            <span class="ring" />
          </div>
          <div v-show="!collapsed" class="brand-txt">
            <div class="name">{{ store.profile.name }}</div>
            <div class="sub">{{ store.profile.role }}</div>
          </div>
        </div>
      </template>

      <div class="pf-card">
        <div class="pf-top">
          <div class="pf-avatar mono">{{ store.profile.avatar }}</div>
          <div class="pf-id">
            <div class="pf-name">{{ store.profile.name }}</div>
            <div class="pf-role">{{ store.profile.role }}</div>
          </div>
        </div>
        <div class="pf-row"><span class="pf-k">学校</span><span class="pf-v">{{ store.profile.school }}</span></div>
        <div class="pf-row"><span class="pf-k">账号</span><span class="pf-v mono">{{ store.userRaw?.username || '—' }}</span></div>
        <div class="pf-actions">
          <button class="pf-btn primary" @click="openEdit">✎ 编辑个人信息</button>
          <button class="pf-btn" @click="goSettings">⚙ 战略参数设置</button>
          <button class="pf-btn danger" @click="logout">⏻ 退出登录</button>
        </div>
      </div>
    </NPopover>

    <nav ref="menuEl" class="menu" :class="{ sorting: dragIdx >= 0 }">
      <RouterLink
        v-for="(m, i) in menus"
        :key="m.path"
        :to="m.path"
        class="item"
        :class="{ active: route.path === m.path, dragging: dragIdx === i }"
        :title="collapsed ? m.title : '长按可拖拽排序 · ' + m.title"
        @click.capture="onNavClick"
        @pointerdown="onPointerDown($event, i)"
      >
        <span class="ico">{{ m.icon }}</span>
        <span v-show="!collapsed" class="txt">{{ m.title }}</span>
        <span v-if="!collapsed" class="grip">⠿</span>
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

      <button class="collapse-btn" :title="collapsed ? '展开导航' : '收起导航'" @click="store.toggleSidebar()">
        {{ collapsed ? '»' : '« 收起' }}
      </button>
    </div>

    <!-- 自定义个人信息弹窗 -->
    <NModal v-model:show="showEdit" preset="card" title="编辑个人信息" style="width:420px" :bordered="false">
      <div class="pf-form">
        <div class="field">
          <label class="label-3">昵称</label>
          <NInput v-model:value="form.nickname" placeholder="例如：唐瑞瑞" maxlength="64" />
        </div>
        <div class="field">
          <label class="label-3">头像文字（1~2 字）</label>
          <NInput v-model:value="form.avatar" placeholder="例如：唐" maxlength="2" show-count />
        </div>
        <div class="field">
          <label class="label-3">学校</label>
          <NInput v-model:value="form.school" placeholder="例如：山东航空学院" maxlength="64" />
        </div>
        <div class="field">
          <label class="label-3">身份 / 状态</label>
          <NInput v-model:value="form.role" placeholder="例如：考研备战中" maxlength="64" />
        </div>
      </div>
      <template #footer>
        <div class="pf-footer">
          <NButton quaternary @click="showEdit = false">取消</NButton>
          <NButton type="primary" :loading="saving" @click="saveProfile">保存</NButton>
        </div>
      </template>
    </NModal>
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

/* 品牌（点击打开个人信息窗口；桌面版退出拖拽区保证可点击） */
.brand { display: flex; align-items: center; gap: 10px; padding: 18px 16px 12px; cursor: pointer; border-radius: 14px; -webkit-app-region: no-drag; transition: background 0.15s ease; }
.brand:hover { background: rgba(74, 222, 128, 0.06); }
.brand.mini { justify-content: center; padding: 18px 0 12px; }
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
.grip { margin-left: auto; font-size: 12px; color: var(--text-3); opacity: 0; transition: opacity 0.15s; letter-spacing: -1px; }
.item:hover .grip { opacity: 0.55; }
.menu.sorting { cursor: grabbing; }
.menu.sorting .item { transition: transform 0.12s ease; }
.item.dragging {
  background: rgba(74, 222, 128, 0.14) !important;
  border-color: rgba(74, 222, 128, 0.5) !important;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.5), 0 0 14px rgba(74, 222, 128, 0.25);
  transform: scale(1.03);
  z-index: 3;
  cursor: grabbing;
}
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

/* 头像弹出窗（个人信息卡片）—— NPopover raw 内容 */
.pf-card {
  width: 264px; padding: 14px;
  background: rgba(19, 26, 23, 0.97); border: 1px solid var(--border-strong, rgba(74, 222, 128, 0.18));
  border-radius: 16px; box-shadow: 0 18px 50px rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(14px);
}
.pf-top { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px dashed var(--border); }
.pf-avatar {
  width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
  background: rgba(74, 222, 128, 0.14); border: 1px solid rgba(74, 222, 128, 0.45);
  color: var(--accent); font-size: 16px; flex-shrink: 0; box-shadow: 0 0 16px rgba(74, 222, 128, 0.25);
}
.pf-name { font-size: 14.5px; font-weight: 700; color: var(--text-1); }
.pf-role { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.pf-row { display: flex; justify-content: space-between; gap: 10px; font-size: 11.5px; padding: 5px 0; }
.pf-k { color: var(--text-3); }
.pf-v { color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 170px; }
.pf-actions { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.pf-btn {
  height: 30px; border-radius: 9px; cursor: pointer; font-size: 12px; text-align: center;
  background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); color: var(--text-2);
  transition: all 0.15s ease;
}
.pf-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
.pf-btn.primary { background: rgba(74, 222, 128, 0.12); border-color: rgba(74, 222, 128, 0.4); color: var(--accent); font-weight: 600; }
.pf-btn.danger:hover { color: #f87171; border-color: rgba(248, 113, 113, 0.4); }

.pf-form { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 5px; }
.pf-footer { display: flex; justify-content: flex-end; gap: 10px; }

.collapse-btn {
  height: 30px; border-radius: 10px; cursor: pointer;
  background: transparent; border: 1px solid var(--border); color: var(--text-3); font-size: 11.5px;
}
.collapse-btn:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
</style>
