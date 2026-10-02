/** 前端 CSV 导出：拼表 → Blob 保存（带 BOM，Excel 直接打开不乱码）。 */
import { saveBlob } from './download'

function esc(v) {
  const s = v === null || v === undefined ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export async function downloadCsv(filename, headers, rows) {
  const lines = [headers.map(esc).join(',')]
  for (const r of rows) lines.push(r.map(esc).join(','))
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  return saveBlob(blob, filename)
}
