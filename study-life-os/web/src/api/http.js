import { createDiscreteApi } from 'naive-ui'
import axios from 'axios'

const { message } = createDiscreteApi(['message'])

export const TOKEN_KEY = 'sl_token'

const http = axios.create({ baseURL: '/api/v1', timeout: 40000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) {
      window.dispatchEvent(new CustomEvent('sl-logout'))
    } else if (typeof detail === 'string' && !err.config?.silent) {
      message.error(detail)
    }
    // 结构化错误（如课程冲突 409）交由调用方处理；挂在 e.detail 上
    err.detail = detail
    return Promise.reject(err)
  },
)

export default http
