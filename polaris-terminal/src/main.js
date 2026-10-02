import { createApp } from 'vue'
import naive from 'naive-ui'
import App from './App.vue'
import router from './router'
import './styles/global.css'

const app = createApp(App)

/* 全局错误兜底：任何未捕获异常都记录到控制台，避免静默白屏 */
app.config.errorHandler = (err, _instance, info) => {
  console.error('[未捕获异常]', info, err)
}

app.config.warnHandler = (msg, _instance, trace) => {
  if (import.meta.env.DEV) console.warn('[Vue warn]', msg, trace)
}

app.use(router).use(naive).mount('#app')
