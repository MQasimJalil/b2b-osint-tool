import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,              // allow external access (needed for ngrok)
    port: 3000,
    allowedHosts: [
      'cdfec06b9717.ngrok-free.app', // allow your ngrok domain
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      }
    }
  }
})
