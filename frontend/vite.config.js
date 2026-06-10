import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// dev：前端 5173，/api 代理到後端 8100（免 CORS 煩惱）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8100',
    },
  },
})
