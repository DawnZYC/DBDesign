// vite.config.ts
import { defineConfig } from "file:///sessions/nice-nifty-albattani/mnt/DBDesign/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/nice-nifty-albattani/mnt/DBDesign/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // SSE endpoint: buffering must be disabled, otherwise events only reach
      // the browser in one batch when the stream ends.
      "/api/chat/stream": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Forward each chunk immediately instead of waiting for the response to end.
        selfHandleResponse: false,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["x-accel-buffering"] = "no";
            proxyRes.headers["cache-control"] = "no-cache";
          });
        }
      },
      // Proxy other /api/* to the backend to avoid CORS issues.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvbmljZS1uaWZ0eS1hbGJhdHRhbmkvbW50L0RCRGVzaWduL2Zyb250ZW5kXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvc2Vzc2lvbnMvbmljZS1uaWZ0eS1hbGJhdHRhbmkvbW50L0RCRGVzaWduL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9zZXNzaW9ucy9uaWNlLW5pZnR5LWFsYmF0dGFuaS9tbnQvREJEZXNpZ24vZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCc7XG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtyZWFjdCgpXSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogNTE3MyxcbiAgICBwcm94eToge1xuICAgICAgLy8gU1NFIGVuZHBvaW50OiBidWZmZXJpbmcgbXVzdCBiZSBkaXNhYmxlZCwgb3RoZXJ3aXNlIGV2ZW50cyBvbmx5IHJlYWNoXG4gICAgICAvLyB0aGUgYnJvd3NlciBpbiBvbmUgYmF0Y2ggd2hlbiB0aGUgc3RyZWFtIGVuZHMuXG4gICAgICAnL2FwaS9jaGF0L3N0cmVhbSc6IHtcbiAgICAgICAgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJyxcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICAvLyBGb3J3YXJkIGVhY2ggY2h1bmsgaW1tZWRpYXRlbHkgaW5zdGVhZCBvZiB3YWl0aW5nIGZvciB0aGUgcmVzcG9uc2UgdG8gZW5kLlxuICAgICAgICBzZWxmSGFuZGxlUmVzcG9uc2U6IGZhbHNlLFxuICAgICAgICBjb25maWd1cmU6IChwcm94eSkgPT4ge1xuICAgICAgICAgIHByb3h5Lm9uKCdwcm94eVJlcycsIChwcm94eVJlcykgPT4ge1xuICAgICAgICAgICAgLy8gVGVsbCBDRE5zIC8gaW50ZXJtZWRpYXRlIHByb3hpZXMgbm90IHRvIGJ1ZmZlci5cbiAgICAgICAgICAgIHByb3h5UmVzLmhlYWRlcnNbJ3gtYWNjZWwtYnVmZmVyaW5nJ10gPSAnbm8nO1xuICAgICAgICAgICAgcHJveHlSZXMuaGVhZGVyc1snY2FjaGUtY29udHJvbCddID0gJ25vLWNhY2hlJztcbiAgICAgICAgICB9KTtcbiAgICAgICAgfSxcbiAgICAgIH0sXG4gICAgICAvLyBQcm94eSBvdGhlciAvYXBpLyogdG8gdGhlIGJhY2tlbmQgdG8gYXZvaWQgQ09SUyBpc3N1ZXMuXG4gICAgICAnL2FwaSc6IHtcbiAgICAgICAgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJyxcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgfSxcbiAgICB9LFxuICB9LFxufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQThVLFNBQVMsb0JBQW9CO0FBQzNXLE9BQU8sV0FBVztBQUVsQixJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUEsRUFDakIsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sT0FBTztBQUFBO0FBQUE7QUFBQSxNQUdMLG9CQUFvQjtBQUFBLFFBQ2xCLFFBQVE7QUFBQSxRQUNSLGNBQWM7QUFBQTtBQUFBLFFBRWQsb0JBQW9CO0FBQUEsUUFDcEIsV0FBVyxDQUFDLFVBQVU7QUFDcEIsZ0JBQU0sR0FBRyxZQUFZLENBQUMsYUFBYTtBQUVqQyxxQkFBUyxRQUFRLG1CQUFtQixJQUFJO0FBQ3hDLHFCQUFTLFFBQVEsZUFBZSxJQUFJO0FBQUEsVUFDdEMsQ0FBQztBQUFBLFFBQ0g7QUFBQSxNQUNGO0FBQUE7QUFBQSxNQUVBLFFBQVE7QUFBQSxRQUNOLFFBQVE7QUFBQSxRQUNSLGNBQWM7QUFBQSxNQUNoQjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
