<script setup>
import { darkTheme } from 'naive-ui'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AiAssistant from './components/AiAssistant.vue'
import { useUserStore } from './stores/user'
import { geekOverrides } from './theme/geek'

const route = useRoute()
const userStore = useUserStore()
const showAi = computed(() => userStore.isLoggedIn && route.name !== 'login')
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="geekOverrides">
    <n-message-provider placement="top">
      <n-dialog-provider>
        <n-notification-provider placement="bottom-right">
          <router-view />
          <AiAssistant v-if="showAi" />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>
