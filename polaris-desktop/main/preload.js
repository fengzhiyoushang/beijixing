/*
 * preload：以 contextBridge 暴露极小桌面能力。
 * 渲染端（Vue）检测 window.electronAPI 存在时走原生保存，否则保持浏览器 blob 下载，
 * Web 端行为不受影响。
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  /**
   * 原生"另存为"对话框保存文件内容。
   * @param {string} defaultName 默认文件名
   * @param {Uint8Array|ArrayBuffer} data 文件字节
   * @returns {Promise<{saved: boolean, path?: string}>}
   */
  saveBlob: (defaultName, data) =>
    ipcRenderer.invoke('save-blob', { defaultName, data: data instanceof ArrayBuffer ? new Uint8Array(data) : data }),
  // 沙箱预加载脚本无法直接使用 shell，须经 IPC 交给主进程用系统默认浏览器打开
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
