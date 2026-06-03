import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const tunnelHosts = ['.ngrok-free.app', '.ngrok.app', '.ngrok.io', '.trycloudflare.com']

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3100,
    strictPort: true,
    allowedHosts: tunnelHosts,
    proxy: {
      '/api': 'http://localhost:8000',
      '/tg': {
        target: 'http://localhost:8080',
        rewrite: (path) => path.replace(/^\/tg/, ''),
      },
    },
  },
  preview: {
    allowedHosts: tunnelHosts,
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: './src/test/setup.ts',
    exclude: ['node_modules/**', 'dist/**', 'tests/e2e/**'],
    css: true,
  },
})
