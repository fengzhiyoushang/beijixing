import { createPinia } from 'pinia'
import naive from 'naive-ui'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles/global.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')

window.addEventListener('sl-logout', () => {
  localStorage.removeItem('sl_token')
  router.push('/login')
})
