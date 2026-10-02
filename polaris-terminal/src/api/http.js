/**
 * HTTP 封装：fetch + JWT + 统一错误 + SSE 流式。
 * 后端地址通过环境变量 VITE_API_BASE 覆盖，默认走 vite 代理 /api/v1。
 */
export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const TOKEN_KEY = 'pl_token'
const USER_KEY = 'pl_user'

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
}
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
export function getCachedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}
export function setCachedUser(user) {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}

function buildUrl(path, params) {
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE
  let url = `${base}${path.startsWith('/') ? path : `/${path}`}`
  if (params) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, v)
    })
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  return url
}

async function handle(resp) {
  if (resp.status === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('pl-logout'))
    throw new ApiError('登录已过期，请重新登录', 401)
  }
  const text = await resp.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!resp.ok) {
    const message =
      (body && (body.message || body.detail?.message)) ||
      (typeof body === 'string' ? body.slice(0, 120) : '') ||
      `请求失败（HTTP ${resp.status}）`
    throw new ApiError(message, resp.status, body)
  }
  return body
}

export async function request(method, path, { data, params, form } = {}) {
  const headers = {}
  let body
  if (form) {
    body = form
  } else if (data !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(data)
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const resp = await fetch(buildUrl(path, params), { method, headers, body })
  return handle(resp)
}

export const http = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, data, params) => request('POST', path, { data, params }),
  put: (path, data, params) => request('PUT', path, { data, params }),
  patch: (path, data, params) => request('PATCH', path, { data, params }),
  del: (path, params) => request('DELETE', path, { params }),
  upload: (path, file, params) => {
    const form = new FormData()
    form.append('file', file)
    return request('POST', path, { form, params })
  },
  /** 自定义 FormData（字段名/附加字段由调用方决定），params 仍走 query */
  uploadForm: (path, form, params) => request('POST', path, { form, params }),
}

/**
 * SSE 流式对话：解析后端的 event/meta|tool|token|done|error。
 * 返回 { abort() } 供「停止生成」使用。
 */
export function streamChat(payload, handlers = {}) {
  const controller = new AbortController()

  ;(async () => {
    try {
      const resp = await fetch(buildUrl('/ai/chat/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '')
        throw new ApiError(text?.slice(0, 160) || `流式请求失败（HTTP ${resp.status}）`, resp.status)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let event = 'message'

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const raw of lines) {
          const line = raw.trim()
          if (!line) continue
          if (line.startsWith('event:')) {
            event = line.slice(6).trim()
            continue
          }
          if (!line.startsWith('data:')) continue
          let data = {}
          try {
            data = JSON.parse(line.slice(5).trim())
          } catch {
            data = { content: line.slice(5).trim() }
          }
          if (event === 'meta') handlers.onMeta?.(data)
          else if (event === 'tool') handlers.onTool?.(data)
          else if (event === 'token') handlers.onToken?.(data.content || '')
          else if (event === 'done') handlers.onDone?.(data)
          else if (event === 'error') handlers.onError?.(new ApiError(data.message || 'AI 服务异常'))
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      handlers.onError?.(err)
    }
  })()

  return {
    abort: () => controller.abort(),
  }
}
