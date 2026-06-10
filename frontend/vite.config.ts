import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // SSE endpoint: buffering must be disabled, otherwise events only reach
      // the browser in one batch when the stream ends.
      '/api/chat/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Forward each chunk immediately instead of waiting for the response to end.
        selfHandleResponse: false,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // Tell CDNs / intermediate proxies not to buffer.
            proxyRes.headers['x-accel-buffering'] = 'no';
            proxyRes.headers['cache-control'] = 'no-cache';
          });
        },
      },
      // Proxy other /api/* to the backend to avoid CORS issues.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
