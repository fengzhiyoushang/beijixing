import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5200,
    host: '127.0.0.1',
    // 已接入真实后端：/api 与 /uploads 代理到 FastAPI(8000)
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/uploads': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
    watch: {
      // 忽略编辑器/工具产生的临时目录，避免 Windows 下 EBUSY 让 dev server 崩溃
      ignored: ['**/.*.tmpdir/**', '**/.*.tmp/**', '**/dist/**'],
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
  },
})
