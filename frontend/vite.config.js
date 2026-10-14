import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// dev: frontend on 5173, /api proxied to the backend on 8100 (no CORS hassle)
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8100',
    },
  },
})
