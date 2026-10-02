<script setup>
import { onErrorCaptured, ref } from 'vue'
import SideNav from './SideNav.vue'
import TopBar from './TopBar.vue'
import AiAssistant from './AiAssistant.vue'
import { store } from '../store'

/**
 * 视图级错误边界：
 * 单个页面渲染异常时只替换内容区并给出重试入口，绝不白屏、也不影响侧栏与后续导航。
 */
const viewError = ref('')
onErrorCaptured((err, _instance, info) => {
  viewError.value = `${err?.message || err}${info ? ` · ${info}` : ''}`
  console.error('[视图渲染异常]', err, info)
  return false                     // 阻止向上冒泡，避免整个应用挂掉
})

function retryRender() {
  viewError.value = ''
}

async function retryData() {
  viewError.value = ''
  await store.refresh()
}
</script>

<template>
  <div class="shell">
    <SideNav />
    <div class="main">
      <TopBar />
      <section class="content">
        <div v-if="viewError" class="view-error">
          <div class="ve-icon">⚠</div>
          <div class="ve-title">该页面渲染出错（已隔离，其它页面不受影响）</div>
          <div class="ve-msg mono">{{ viewError }}</div>
          <div class="ve-actions">
            <button class="ve-btn" @click="retryRender">重试渲染</button>
            <button class="ve-btn ghost" @click="retryData">重新拉取数据</button>
          </div>
        </div>
        <RouterView v-else v-slot="{ Component, route }">
          <component :is="Component" :key="route.path" />
        </RouterView>
      </section>
    </div>
    <AiAssistant />
  </div>
</template>

<style scoped>
/* 背景交给 body 的柔光层，这里保持透明以露出光晕 */
.shell { display: flex; height: 100vh; overflow: hidden; background: transparent; position: relative; z-index: 1; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.content { flex: 1; overflow-y: auto; overflow-x: hidden; background: transparent; }

.view-error {
  margin: 48px auto 0; max-width: 560px; text-align: center;
  border: 1px solid rgba(248, 113, 113, 0.32); border-radius: var(--radius);
  background: rgba(248, 113, 113, 0.06); padding: 26px 24px;
}
.ve-icon { font-size: 26px; color: var(--red); }
.ve-title { margin-top: 10px; font-size: 14px; color: #fca5a5; }
.ve-msg { margin-top: 10px; font-size: 11.5px; color: var(--text-3); word-break: break-all; }
.ve-actions { margin-top: 18px; display: flex; gap: 10px; justify-content: center; }
.ve-btn {
  padding: 6px 16px; border-radius: 999px; cursor: pointer; font-size: 12.5px;
  background: var(--accent); color: #06170d; border: none; font-weight: 650;
}
.ve-btn.ghost { background: transparent; color: var(--text-2); border: 1px solid var(--border); }
.ve-btn.ghost:hover { color: var(--accent); border-color: rgba(74, 222, 128, 0.4); }
</style>
