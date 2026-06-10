// vitest.config.ts
import { defineConfig as defineConfig2, mergeConfig } from "file:///sessions/nice-nifty-albattani/mnt/DBDesign/frontend/node_modules/vitest/dist/config.js";

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

// vitest.config.ts
var vitest_config_default = mergeConfig(
  vite_config_default,
  defineConfig2({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      coverage: {
        provider: "v8",
        reporter: ["text", "lcov", "html"],
        reportsDirectory: "./coverage",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/**/*.d.ts",
          "src/main.tsx",
          "src/types.ts",
          "src/__tests__/**",
          "src/test/**"
        ]
      }
    }
  })
);
export {
  vitest_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZXN0LmNvbmZpZy50cyIsICJ2aXRlLmNvbmZpZy50cyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiY29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2Rpcm5hbWUgPSBcIi9zZXNzaW9ucy9uaWNlLW5pZnR5LWFsYmF0dGFuaS9tbnQvREJEZXNpZ24vZnJvbnRlbmRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIi9zZXNzaW9ucy9uaWNlLW5pZnR5LWFsYmF0dGFuaS9tbnQvREJEZXNpZ24vZnJvbnRlbmQvdml0ZXN0LmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vc2Vzc2lvbnMvbmljZS1uaWZ0eS1hbGJhdHRhbmkvbW50L0RCRGVzaWduL2Zyb250ZW5kL3ZpdGVzdC5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcsIG1lcmdlQ29uZmlnIH0gZnJvbSAndml0ZXN0L2NvbmZpZyc7XG5pbXBvcnQgdml0ZUNvbmZpZyBmcm9tICcuL3ZpdGUuY29uZmlnJztcblxuLy8gVml0ZXN0IHJldXNlcyB0aGUgZXhpc3RpbmcgVml0ZSBwbHVnaW4gcGlwZWxpbmUgKFJlYWN0LCBldGMuKSBhbmQgYWRkcyB0aGVcbi8vIGpzZG9tIGVudmlyb25tZW50IHBsdXMgdGhlIGdsb2JhbCBqZXN0LWRvbSBtYXRjaGVycyB2aWEgc2V0dXBGaWxlcy5cbmV4cG9ydCBkZWZhdWx0IG1lcmdlQ29uZmlnKFxuICB2aXRlQ29uZmlnLFxuICBkZWZpbmVDb25maWcoe1xuICAgIHRlc3Q6IHtcbiAgICAgIGdsb2JhbHM6IHRydWUsXG4gICAgICBlbnZpcm9ubWVudDogJ2pzZG9tJyxcbiAgICAgIHNldHVwRmlsZXM6ICcuL3NyYy90ZXN0L3NldHVwLnRzJyxcbiAgICAgIGNzczogdHJ1ZSxcbiAgICAgIGNvdmVyYWdlOiB7XG4gICAgICAgIHByb3ZpZGVyOiAndjgnLFxuICAgICAgICByZXBvcnRlcjogWyd0ZXh0JywgJ2xjb3YnLCAnaHRtbCddLFxuICAgICAgICByZXBvcnRzRGlyZWN0b3J5OiAnLi9jb3ZlcmFnZScsXG4gICAgICAgIGluY2x1ZGU6IFsnc3JjLyoqLyoue3RzLHRzeH0nXSxcbiAgICAgICAgZXhjbHVkZTogW1xuICAgICAgICAgICdzcmMvKiovKi5kLnRzJyxcbiAgICAgICAgICAnc3JjL21haW4udHN4JyxcbiAgICAgICAgICAnc3JjL3R5cGVzLnRzJyxcbiAgICAgICAgICAnc3JjL19fdGVzdHNfXy8qKicsXG4gICAgICAgICAgJ3NyYy90ZXN0LyoqJyxcbiAgICAgICAgXSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSksXG4pO1xuIiwgImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvbmljZS1uaWZ0eS1hbGJhdHRhbmkvbW50L0RCRGVzaWduL2Zyb250ZW5kXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvc2Vzc2lvbnMvbmljZS1uaWZ0eS1hbGJhdHRhbmkvbW50L0RCRGVzaWduL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9zZXNzaW9ucy9uaWNlLW5pZnR5LWFsYmF0dGFuaS9tbnQvREJEZXNpZ24vZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCc7XG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtyZWFjdCgpXSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogNTE3MyxcbiAgICBwcm94eToge1xuICAgICAgLy8gU1NFIGVuZHBvaW50OiBidWZmZXJpbmcgbXVzdCBiZSBkaXNhYmxlZCwgb3RoZXJ3aXNlIGV2ZW50cyBvbmx5IHJlYWNoXG4gICAgICAvLyB0aGUgYnJvd3NlciBpbiBvbmUgYmF0Y2ggd2hlbiB0aGUgc3RyZWFtIGVuZHMuXG4gICAgICAnL2FwaS9jaGF0L3N0cmVhbSc6IHtcbiAgICAgICAgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJyxcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICAvLyBGb3J3YXJkIGVhY2ggY2h1bmsgaW1tZWRpYXRlbHkgaW5zdGVhZCBvZiB3YWl0aW5nIGZvciB0aGUgcmVzcG9uc2UgdG8gZW5kLlxuICAgICAgICBzZWxmSGFuZGxlUmVzcG9uc2U6IGZhbHNlLFxuICAgICAgICBjb25maWd1cmU6IChwcm94eSkgPT4ge1xuICAgICAgICAgIHByb3h5Lm9uKCdwcm94eVJlcycsIChwcm94eVJlcykgPT4ge1xuICAgICAgICAgICAgLy8gVGVsbCBDRE5zIC8gaW50ZXJtZWRpYXRlIHByb3hpZXMgbm90IHRvIGJ1ZmZlci5cbiAgICAgICAgICAgIHByb3h5UmVzLmhlYWRlcnNbJ3gtYWNjZWwtYnVmZmVyaW5nJ10gPSAnbm8nO1xuICAgICAgICAgICAgcHJveHlSZXMuaGVhZGVyc1snY2FjaGUtY29udHJvbCddID0gJ25vLWNhY2hlJztcbiAgICAgICAgICB9KTtcbiAgICAgICAgfSxcbiAgICAgIH0sXG4gICAgICAvLyBQcm94eSBvdGhlciAvYXBpLyogdG8gdGhlIGJhY2tlbmQgdG8gYXZvaWQgQ09SUyBpc3N1ZXMuXG4gICAgICAnL2FwaSc6IHtcbiAgICAgICAgdGFyZ2V0OiAnaHR0cDovL2xvY2FsaG9zdDo4MDAwJyxcbiAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgfSxcbiAgICB9LFxuICB9LFxufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQWtWLFNBQVMsZ0JBQUFBLGVBQWMsbUJBQW1COzs7QUNBOUMsU0FBUyxvQkFBb0I7QUFDM1csT0FBTyxXQUFXO0FBRWxCLElBQU8sc0JBQVEsYUFBYTtBQUFBLEVBQzFCLFNBQVMsQ0FBQyxNQUFNLENBQUM7QUFBQSxFQUNqQixRQUFRO0FBQUEsSUFDTixNQUFNO0FBQUEsSUFDTixPQUFPO0FBQUE7QUFBQTtBQUFBLE1BR0wsb0JBQW9CO0FBQUEsUUFDbEIsUUFBUTtBQUFBLFFBQ1IsY0FBYztBQUFBO0FBQUEsUUFFZCxvQkFBb0I7QUFBQSxRQUNwQixXQUFXLENBQUMsVUFBVTtBQUNwQixnQkFBTSxHQUFHLFlBQVksQ0FBQyxhQUFhO0FBRWpDLHFCQUFTLFFBQVEsbUJBQW1CLElBQUk7QUFDeEMscUJBQVMsUUFBUSxlQUFlLElBQUk7QUFBQSxVQUN0QyxDQUFDO0FBQUEsUUFDSDtBQUFBLE1BQ0Y7QUFBQTtBQUFBLE1BRUEsUUFBUTtBQUFBLFFBQ04sUUFBUTtBQUFBLFFBQ1IsY0FBYztBQUFBLE1BQ2hCO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFDRixDQUFDOzs7QUR6QkQsSUFBTyx3QkFBUTtBQUFBLEVBQ2I7QUFBQSxFQUNBQyxjQUFhO0FBQUEsSUFDWCxNQUFNO0FBQUEsTUFDSixTQUFTO0FBQUEsTUFDVCxhQUFhO0FBQUEsTUFDYixZQUFZO0FBQUEsTUFDWixLQUFLO0FBQUEsTUFDTCxVQUFVO0FBQUEsUUFDUixVQUFVO0FBQUEsUUFDVixVQUFVLENBQUMsUUFBUSxRQUFRLE1BQU07QUFBQSxRQUNqQyxrQkFBa0I7QUFBQSxRQUNsQixTQUFTLENBQUMsbUJBQW1CO0FBQUEsUUFDN0IsU0FBUztBQUFBLFVBQ1A7QUFBQSxVQUNBO0FBQUEsVUFDQTtBQUFBLFVBQ0E7QUFBQSxVQUNBO0FBQUEsUUFDRjtBQUFBLE1BQ0Y7QUFBQSxJQUNGO0FBQUEsRUFDRixDQUFDO0FBQ0g7IiwKICAibmFtZXMiOiBbImRlZmluZUNvbmZpZyIsICJkZWZpbmVDb25maWciXQp9Cg==
