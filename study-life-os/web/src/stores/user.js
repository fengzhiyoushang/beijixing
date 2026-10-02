import { defineStore } from 'pinia'
import { authApi } from '../api'
import { TOKEN_KEY } from '../api/http'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    nickname: (s) => s.user?.nickname || '同学',
  },
  actions: {
    _afterAuth(data) {
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem(TOKEN_KEY, data.access_token)
    },
    async login(payload) {
      this._afterAuth(await authApi.login(payload))
    },
    async register(payload) {
      this._afterAuth(await authApi.register(payload))
    },
    async fetchMe() {
      if (!this.token) return
      try {
        this.user = await authApi.me()
      } catch { /* 401 由拦截器处理 */ }
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
