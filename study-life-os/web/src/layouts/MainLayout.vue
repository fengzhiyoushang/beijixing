<script setup>
import { computed, h, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const glyph = (g) => () => h('span', { class: 'menu-glyph' }, g)
const menuOptions = [
  { label: '总览仪表盘', key: 'dashboard', icon: glyph('▦') },
  { label: '课程表管理', key: 'timetable', icon: glyph('▤') },
  { label: 'DDL 任务', key: 'tasks', icon: glyph('☑') },
  { label: '空教室分析', key: 'classroom', icon: glyph('▣') },
  { label: '考研规划', key: 'kaoyan', icon: glyph('◎') },
  { label: '知识库', key: 'knowledge', icon: glyph('≡') },
  { label: '个人财务', key: 'finance', icon: glyph('¥') },
  { label: '个人健康', key: 'health', icon: glyph('♥') },
]

const active = computed(() => route.name)
const now = new Date()
const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} 周${'日一二三四五六'[now.getDay()]}`

onMounted(() => userStore.fetchMe())

function onUserAction(key) {
  if (key === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}
</script>

<template>
  <n-layout has-sider style="height: 100vh" :content-style="`background: transparent`">
    <n-layout-sider
      bordered
      :width="218"
      collapse-mode="width"
      :collapsed-width="60"
      show-trigger="bar"
      :native-scrollbar="false"
      class="sider"
    >
      <div class="brand">
        <div class="brand-line mono glow-text"><span class="prompt">❯</span> StudyLifeOS</div>
        <div class="brand-sub mono">AI·TERMINAL v0.1 — {{ dateStr }}</div>
      </div>
      <n-menu
        :value="active"
        :options="menuOptions"
        :collapsed-width="60"
        @update:value="(k) => router.push('/' + k)"
      />
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="topbar">
        <span class="mono path-line">~/terminal/{{ route.name || 'dashboard' }} $</span>
        <n-dropdown
          trigger="click"
          :options="[{ label: '退出登录', key: 'logout' }]"
          @select="onUserAction"
        >
          <div class="user-chip">
            <span class="avatar mono">{{ (userStore.nickname || 'U')[0] }}</span>
            <span>{{ userStore.nickname }}</span>
          </div>
        </n-dropdown>
      </n-layout-header>
      <n-layout-content :native-scrollbar="false" content-style="min-height: calc(100vh - 57px)">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.sider { background: rgba(9, 14, 26, 0.88) !important; }
.brand { padding: 18px 14px 10px; }
.brand-line { font-size: 17px; font-weight: 700; color: #00e5a0; letter-spacing: 1px; white-space: nowrap; }
.prompt { color: #38bdf8; }
.brand-sub { margin-top: 4px; font-size: 10px; color: #5b7290; letter-spacing: 1px; white-space: nowrap; overflow: hidden; }
:deep(.menu-glyph) { font-size: 16px; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  height: 56px; padding: 0 20px; background: rgba(11, 17, 31, 0.9);
}
.path-line { color: #5b7290; font-size: 13px; }
.user-chip { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #c9d6e8; font-size: 13px; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(135deg, #00e5a0, #38bdf8);
  color: #04110c; font-weight: 700; display: flex; align-items: center; justify-content: center;
}
</style>
