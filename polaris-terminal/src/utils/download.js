/**
 * 统一文件保存：桌面版（Electron）走原生"另存为"对话框，Web 端保持浏览器 blob 下载。
 * 返回值表示用户是否真正保存了文件（桌面版取消对话框时为 false）。
 */
export async function saveBlob(blob, filename) {
  if (window.electronAPI?.saveBlob) {
    const data = new Uint8Array(await blob.arrayBuffer())
    const r = await window.electronAPI.saveBlob(filename, data)
    return !!r?.saved
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
  return true
}
