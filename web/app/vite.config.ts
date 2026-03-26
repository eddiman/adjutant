import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    port: 3021,
    host: true,
    proxy: {
      '/api/config/browse': {
        target: 'http://localhost:3020',
        changeOrigin: true,
        timeout: 0,        // No socket timeout
        proxyTimeout: 0,   // No proxy timeout — user needs time in Finder
      },
      '/api': {
        target: 'http://localhost:3020',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Split React Flow into its own chunk (large library)
          'react-flow': ['@xyflow/react'],
          // Split TipTap editor into its own chunk
          'tiptap': [
            '@tiptap/react',
            '@tiptap/starter-kit',
            '@tiptap/extension-highlight',
            '@tiptap/extension-placeholder',
            '@tiptap/extension-image',
          ],
        },
      },
    },
  },
})
