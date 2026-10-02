const p = (n) => String(n).padStart(2, '0')

export function fmtTime(d = new Date()) {
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function fmtDate(d = new Date()) {
  return `${d.getMonth() + 1}月${d.getDate()}日 周${'日一二三四五六'[d.getDay()]}`
}

export function fmtShort(iso) {
  if (!iso) return '—'
  return iso.slice(5, 16).replace('T', ' ')
}

/** ISO → 倒计时文案 */
export function countdown(iso, now = Date.now()) {
  const sec = Math.floor((new Date(iso).getTime() - now) / 1000)
  if (isNaN(sec)) return { text: '—', overdue: false }
  if (sec < 0) {
    const day = Math.floor(-sec / 86400)
    return { text: day > 0 ? `已逾期 ${day} 天` : `已逾期 ${Math.floor(-sec / 3600)} 小时`, overdue: true }
  }
  const day = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (day > 0) return { text: `${day} 天 ${p(h)}:${p(m)}:${p(s)}`, overdue: false }
  return { text: `${p(h)}:${p(m)}:${p(s)}`, overdue: false }
}

export function daysUntil(iso) {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000))
}

export function greetingByHour(h = new Date().getHours()) {
  if (h < 5) return '凌晨了，注意休息'
  if (h < 9) return '早上好，新的一天从战略开始'
  if (h < 12) return '上午好，保持专注'
  if (h < 14) return '中午好，记得小憩'
  if (h < 18) return '下午好，稳步推进'
  if (h < 22) return '晚上好，复盘一下今天'
  return '夜深了，明日再战'
}

export const PRIORITY_LABEL = { high: '高', medium: '中', low: '低' }
export const PRIORITY_TONE = { high: 'red', medium: 'yellow', low: 'green' }
