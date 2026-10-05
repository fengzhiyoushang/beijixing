/**
 * 统一"在外部浏览器（Edge）打开链接"：
 * - 桌面版：window.electronAPI.openExternal → shell.openExternal（系统默认浏览器）
 * - Web 版：window.open；被弹窗拦截时降级为当前页跳转
 * 自动补全缺失协议并校验合法性，避免点击无响应。
 */
export function normalizeExternalUrl(raw) {
  let u = String(raw || '').trim()
  if (!u) return ''
  if (/^javascript:/i.test(u)) return ''
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(u)) u = 'https://' + u
  try {
    const p = new URL(u)
    if (p.protocol !== 'http:' && p.protocol !== 'https:') return ''
    return p.href
  } catch {
    return ''
  }
}

export function openExternal(raw) {
  const url = normalizeExternalUrl(raw)
  if (!url) return false
  const api = typeof window !== 'undefined' ? window.electronAPI : null
  if (api?.openExternal) {
    try {
      api.openExternal(url)
      return true
    } catch { /* 回退到 Web 方式 */ }
  }
  try {
    // 注意：不能带 noopener —— 规范下带 noopener 时 window.open 恒返回 null，
    // 会被误判为"弹窗被拦截"而错误触发当前页跳转
    const w = window.open(url, '_blank')
    if (!w || w.closed) window.location.href = url   // 弹窗确实被拦截：当前页跳转
    return true
  } catch {
    window.location.href = url
    return true
  }
}
