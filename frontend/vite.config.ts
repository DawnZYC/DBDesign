import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // SSE 端点：必须禁用缓冲，否则事件会等到流结束才一次性到达浏览器
      '/api/chat/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // 让 http-proxy 把每一块数据立即转发，不等响应结束
        selfHandleResponse: false,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // 告知 CDN / 中间代理不要缓冲
            proxyRes.headers['x-accel-buffering'] = 'no';
            proxyRes.headers['cache-control'] = 'no-cache';
          });
        },
      },
      // 其他 /api/* 走普通代理
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
