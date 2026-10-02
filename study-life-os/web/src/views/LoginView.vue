<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const tab = ref('login')
const loading = ref(false)
const form = ref({ username: 'admin', password: 'admin123', nickname: '' })

async function submit() {
  loading.value = true
  try {
    if (tab.value === 'login') await userStore.login({ username: form.value.username, password: form.value.password })
    else await userStore.register({ username: form.value.username, password: form.value.password, nickname: form.value.nickname })
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="logo mono glow-text">❯ StudyLifeOS</div>
      <div class="slogan">个人学习 · 工作 · 生活 管理终端</div>
      <n-tabs v-model:value="tab" type="segment" justify="space-around" class="tabs">
        <n-tab-pane name="login" tab="登录" />
        <n-tab-pane name="register" tab="注册" />
      </n-tabs>
      <n-space vertical :size="14" style="margin-top: 16px">
        <n-input v-model:value="form.username" placeholder="用户名（演示 admin）" size="large" @keyup.enter="submit" />
        <n-input v-model:value="form.password" type="password" placeholder="密码（演示 admin123）" size="large" show-password-on="click" @keyup.enter="submit" />
        <n-input v-if="tab === 'register'" v-model:value="form.nickname" placeholder="昵称（可选）" size="large" />
        <n-button type="primary" size="large" block :loading="loading" class="enter-btn" @click="submit">
          <span class="mono">[ {{ tab === 'login' ? 'ENTER TERMINAL ⏎' : 'CREATE ACCOUNT ⏎' }} ]</span>
        </n-button>
      </n-space>
      <div class="hint mono">Web 深度管理端 · 数据与小程序实时联动</div>
    </div>
  </div>
</template>

<style scoped>
.login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.login-card {
  width: 400px; padding: 36px 34px 26px; border-radius: 14px;
  background: rgba(13, 20, 36, 0.92); border: 1px solid rgba(0, 229, 160, 0.22);
  box-shadow: 0 0 44px rgba(0, 229, 160, 0.1), inset 0 0 32px rgba(0, 0, 0, 0.35);
}
.logo { font-size: 26px; font-weight: 800; color: #00e5a0; }
.slogan { color: #5b7290; font-size: 12px; margin: 6px 0 20px; letter-spacing: 1px; }
.enter-btn { background: linear-gradient(135deg, #00c98a, #0aa8d8); border: none; letter-spacing: 1px; }
.hint { margin-top: 18px; text-align: center; color: #3f5675; font-size: 11px; }
</style>
