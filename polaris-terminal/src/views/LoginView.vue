<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, useMessage } from 'naive-ui'
import { store } from '../store'

const router = useRouter()
const message = useMessage()

const mode = ref('login')            // login | register
const form = ref({ username: 'admin', password: 'admin123', nickname: '', email: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!form.value.username || !form.value.password) {
    error.value = '请填写账号与密码'
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await store.login(form.value.username.trim(), form.value.password)
      message.success(`欢迎回来，${store.profile.name}`)
    } else {
      await store.register({
        username: form.value.username.trim(),
        password: form.value.password,
        nickname: form.value.nickname || undefined,
        email: form.value.email || undefined,
      })
      message.success('注册成功，已自动登录')
    }
    router.push('/')
  } catch (err) {
    error.value = err.message || '登录失败'
  } finally {
    loading.value = false
  }
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}
</script>

<template>
  <div class="login-wrap">
    <div class="grid-bg" />
    <div class="card">
      <div class="brand">
        <div class="logo"><span class="star">✦</span><span class="ring" /></div>
        <div>
          <div class="name">北极星 · 个人战略终端</div>
          <div class="en mono">POLARIS · PERSONAL STRATEGY TERMINAL</div>
        </div>
      </div>

      <div class="tabs">
        <button class="tab" :class="{ on: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button class="tab" :class="{ on: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <div class="form">
        <label class="label-3">账号</label>
        <NInput v-model:value="form.username" placeholder="用户名" @keyup.enter="submit" />

        <label class="label-3">密码</label>
        <NInput v-model:value="form.password" type="password" show-password-on="click"
                placeholder="密码" @keyup.enter="submit" />

        <template v-if="mode === 'register'">
          <label class="label-3">昵称（可选）</label>
          <NInput v-model:value="form.nickname" placeholder="如：北极星同学" />
          <label class="label-3">邮箱（可选）</label>
          <NInput v-model:value="form.email" placeholder="用于找回账号" />
        </template>

        <div v-if="error" class="err">⚠ {{ error }}</div>

        <NButton type="primary" block :loading="loading" @click="submit">
          {{ mode === 'login' ? '进入终端' : '注册并进入' }}
        </NButton>
      </div>

      <div class="hint mono">
        演示账号：admin / admin123　·　后端：{{ store.settings.backendUrl === '—' ? '未连接' : '已连接' }}<br />
        数据与微信小程序共用同一后端（登录同一账号即可双端同步）
      </div>
      <button class="link mono" @click="switchMode">
        {{ mode === 'login' ? '没有账号？点此注册 →' : '已有账号？返回登录 →' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  position: relative; min-height: 100vh; display: grid; place-items: center;
  background: radial-gradient(1200px 600px at 50% -10%, rgba(74, 222, 128, 0.08), transparent), var(--bg);
  overflow: hidden;
}
.grid-bg {
  position: absolute; inset: 0; opacity: 0.35;
  background-image: linear-gradient(rgba(42, 42, 42, 0.55) 1px, transparent 1px),
    linear-gradient(90deg, rgba(42, 42, 42, 0.55) 1px, transparent 1px);
  background-size: 40px 40px;
}
.card {
  position: relative; width: 420px; max-width: calc(100vw - 32px);
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 26px 26px 20px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.55), 0 0 40px rgba(74, 222, 128, 0.06);
}
.brand { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.logo { position: relative; width: 38px; height: 38px; display: grid; place-items: center; }
.star { color: var(--accent); font-size: 22px; text-shadow: 0 0 16px var(--accent); }
.ring { position: absolute; inset: 0; border: 1px solid rgba(74, 222, 128, 0.35); border-radius: 50%; }
.name { font-size: 15px; font-weight: 700; letter-spacing: 1px; }
.en { font-size: 9px; color: var(--text-3); letter-spacing: 1.2px; }

.tabs { display: flex; gap: 6px; margin-bottom: 16px; }
.tab {
  flex: 1; padding: 8px 0; border-radius: 8px; cursor: pointer; font-size: 13px;
  background: transparent; border: 1px solid var(--border); color: var(--text-2);
}
.tab.on { color: var(--accent); border-color: rgba(74, 222, 128, 0.5); background: rgba(74, 222, 128, 0.08); }

.form { display: flex; flex-direction: column; gap: 8px; }
.form .label-3 { margin-top: 6px; }
.err { color: #f87171; font-size: 12px; padding: 6px 0; }
.hint { margin-top: 16px; font-size: 10.5px; color: var(--text-3); line-height: 1.7; text-align: center; }
.link { margin-top: 10px; background: none; border: none; color: var(--accent); font-size: 11px; cursor: pointer; }
</style>
