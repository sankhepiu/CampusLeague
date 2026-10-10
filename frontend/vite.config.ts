import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The backend sends no CORS headers by design (proxy instead of CORS,
      // per agreement with the backend team) — without this, every browser
      // request to the API is cross-origin and gets blocked outright.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Receipt images etc. come back from the backend as /media/... URLs.
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
