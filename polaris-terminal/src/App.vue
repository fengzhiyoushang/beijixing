<script setup>
import { onMounted, ref } from 'vue'
import { darkTheme, dateZhCN, NConfigProvider, NDialogProvider, NMessageProvider,
         NNotificationProvider, NSkeleton, zhCN } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { polarisOverrides } from './theme/polaris'
import AppLayout from './components/AppLayout.vue'
import { store } from './store'

const route = useRoute()
const router = useRouter()
const booting = ref(true)

onMounted(async () => {
  window.addEventListener('pl-logout', () => {
    booting.value = false
    if (route.path !== '/login') router.push('/login')
  })
  if (route.path !== '/login') {
    const ok = await store.bootstrap()
    if (!ok) router.push('/login')
  }
  booting.value = false
})
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="polarisOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <!-- 启动加载态 -->
          <div v-if="booting" class="boot">
            <div class="boot-card">
              <div class="star">✦</div>
              <div class="title">北极星 · 正在连接后端…</div>
              <NSkeleton text :repeat="3" style="margin-top: 14px" />
            </div>
          </div>

          <!-- 登录页（无布局） -->
          <RouterView v-else-if="route.meta.plain" />

          <!-- 主应用 -->
          <AppLayout v-else />

          <!-- 全局错误提示条 -->
          <div v-if="!booting && store.errors.length && !route.meta.plain" class="err-bar">
            <span class="dot dot-red" />
            <span class="mono">{{ store.errors.length }} 项数据加载失败：{{ store.errors[0] }}</span>
            <button class="retry mono" @click="store.refresh()">重试</button>
          </div>
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.boot { min-height: 100vh; display: grid; place-items: center; background: #121212; }
.boot-card {
  width: 360px; padding: 28px; background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); text-align: center;
}
.star { font-size: 30px; color: var(--accent); text-shadow: 0 0 20px var(--accent); }
.title { margin-top: 10px; color: var(--text-2); font-size: 13px; }

.err-bar {
  position: fixed; left: 50%; transform: translateX(-50%); bottom: 18px; z-index: 99;
  display: flex; align-items: center; gap: 10px;
  background: rgba(248, 113, 113, 0.1); border: 1px solid rgba(248, 113, 113, 0.4);
  color: #fca5a5; font-size: 12px; padding: 8px 14px; border-radius: 999px;
  backdrop-filter: blur(6px);
}
.retry { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 12px; }
</style>
