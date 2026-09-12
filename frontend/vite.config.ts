import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Local dev only: `npm run dev` proxies API calls to the FastAPI dev
    // server (uvicorn --reload on :8000) so the SPA can call same-origin
    // paths. In production the built app is served BY that same FastAPI
    // process, so no proxy/CORS is needed there.
    proxy: {
      '^/(auth|brokers|me|health)': 'http://localhost:8000',
    },
  },
})
