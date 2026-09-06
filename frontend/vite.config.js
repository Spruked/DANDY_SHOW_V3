import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.DANDY_API_TARGET || 'http://127.0.0.1:8110'
const wsTarget = process.env.DANDY_WS_TARGET || apiTarget.replace(/^http/i, 'ws')

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5188,
    proxy: {
      '/renders': { target: apiTarget, changeOrigin: true },
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
