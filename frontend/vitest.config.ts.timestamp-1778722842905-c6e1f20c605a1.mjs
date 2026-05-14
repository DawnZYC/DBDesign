// vitest.config.ts
import { defineConfig as defineConfig2, mergeConfig } from "file:///sessions/quirky-exciting-pasteur/mnt/Others/DBDesign/frontend/node_modules/vitest/dist/config.js";

// vite.config.ts
import { defineConfig } from "file:///sessions/quirky-exciting-pasteur/mnt/Others/DBDesign/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/quirky-exciting-pasteur/mnt/Others/DBDesign/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* to the backend to avoid CORS issues.
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
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZXN0LmNvbmZpZy50cyIsICJ2aXRlLmNvbmZpZy50cyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiY29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2Rpcm5hbWUgPSBcIi9zZXNzaW9ucy9xdWlya3ktZXhjaXRpbmctcGFzdGV1ci9tbnQvT3RoZXJzL0RCRGVzaWduL2Zyb250ZW5kXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvc2Vzc2lvbnMvcXVpcmt5LWV4Y2l0aW5nLXBhc3RldXIvbW50L090aGVycy9EQkRlc2lnbi9mcm9udGVuZC92aXRlc3QuY29uZmlnLnRzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9zZXNzaW9ucy9xdWlya3ktZXhjaXRpbmctcGFzdGV1ci9tbnQvT3RoZXJzL0RCRGVzaWduL2Zyb250ZW5kL3ZpdGVzdC5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcsIG1lcmdlQ29uZmlnIH0gZnJvbSAndml0ZXN0L2NvbmZpZyc7XG5pbXBvcnQgdml0ZUNvbmZpZyBmcm9tICcuL3ZpdGUuY29uZmlnJztcblxuLy8gVml0ZXN0IHJldXNlcyB0aGUgZXhpc3RpbmcgVml0ZSBwbHVnaW4gcGlwZWxpbmUgKFJlYWN0LCBldGMuKSBhbmQgYWRkcyB0aGVcbi8vIGpzZG9tIGVudmlyb25tZW50IHBsdXMgdGhlIGdsb2JhbCBqZXN0LWRvbSBtYXRjaGVycyB2aWEgc2V0dXBGaWxlcy5cbmV4cG9ydCBkZWZhdWx0IG1lcmdlQ29uZmlnKFxuICB2aXRlQ29uZmlnLFxuICBkZWZpbmVDb25maWcoe1xuICAgIHRlc3Q6IHtcbiAgICAgIGdsb2JhbHM6IHRydWUsXG4gICAgICBlbnZpcm9ubWVudDogJ2pzZG9tJyxcbiAgICAgIHNldHVwRmlsZXM6ICcuL3NyYy90ZXN0L3NldHVwLnRzJyxcbiAgICAgIGNzczogdHJ1ZSxcbiAgICAgIGNvdmVyYWdlOiB7XG4gICAgICAgIHByb3ZpZGVyOiAndjgnLFxuICAgICAgICByZXBvcnRlcjogWyd0ZXh0JywgJ2xjb3YnLCAnaHRtbCddLFxuICAgICAgICByZXBvcnRzRGlyZWN0b3J5OiAnLi9jb3ZlcmFnZScsXG4gICAgICAgIGluY2x1ZGU6IFsnc3JjLyoqLyoue3RzLHRzeH0nXSxcbiAgICAgICAgZXhjbHVkZTogW1xuICAgICAgICAgICdzcmMvKiovKi5kLnRzJyxcbiAgICAgICAgICAnc3JjL21haW4udHN4JyxcbiAgICAgICAgICAnc3JjL3R5cGVzLnRzJyxcbiAgICAgICAgICAnc3JjL19fdGVzdHNfXy8qKicsXG4gICAgICAgICAgJ3NyYy90ZXN0LyoqJyxcbiAgICAgICAgXSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSksXG4pO1xuIiwgImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvcXVpcmt5LWV4Y2l0aW5nLXBhc3RldXIvbW50L090aGVycy9EQkRlc2lnbi9mcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nlc3Npb25zL3F1aXJreS1leGNpdGluZy1wYXN0ZXVyL21udC9PdGhlcnMvREJEZXNpZ24vZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nlc3Npb25zL3F1aXJreS1leGNpdGluZy1wYXN0ZXVyL21udC9PdGhlcnMvREJEZXNpZ24vZnJvbnRlbmQvdml0ZS5jb25maWcudHNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCc7XG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtyZWFjdCgpXSxcbiAgc2VydmVyOiB7XG4gICAgcG9ydDogNTE3MyxcbiAgICBwcm94eToge1xuICAgICAgLy8gUHJveHkgL2FwaS8qIHRvIHRoZSBiYWNrZW5kIHRvIGF2b2lkIENPUlMgaXNzdWVzLlxuICAgICAgJy9hcGknOiB7XG4gICAgICAgIHRhcmdldDogJ2h0dHA6Ly9sb2NhbGhvc3Q6ODAwMCcsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSxcbn0pO1xuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUFnWCxTQUFTLGdCQUFBQSxlQUFjLG1CQUFtQjs7O0FDQTlDLFNBQVMsb0JBQW9CO0FBQ3pZLE9BQU8sV0FBVztBQUVsQixJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUEsRUFDakIsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sT0FBTztBQUFBO0FBQUEsTUFFTCxRQUFRO0FBQUEsUUFDTixRQUFRO0FBQUEsUUFDUixjQUFjO0FBQUEsTUFDaEI7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7OztBRFZELElBQU8sd0JBQVE7QUFBQSxFQUNiO0FBQUEsRUFDQUMsY0FBYTtBQUFBLElBQ1gsTUFBTTtBQUFBLE1BQ0osU0FBUztBQUFBLE1BQ1QsYUFBYTtBQUFBLE1BQ2IsWUFBWTtBQUFBLE1BQ1osS0FBSztBQUFBLE1BQ0wsVUFBVTtBQUFBLFFBQ1IsVUFBVTtBQUFBLFFBQ1YsVUFBVSxDQUFDLFFBQVEsUUFBUSxNQUFNO0FBQUEsUUFDakMsa0JBQWtCO0FBQUEsUUFDbEIsU0FBUyxDQUFDLG1CQUFtQjtBQUFBLFFBQzdCLFNBQVM7QUFBQSxVQUNQO0FBQUEsVUFDQTtBQUFBLFVBQ0E7QUFBQSxVQUNBO0FBQUEsVUFDQTtBQUFBLFFBQ0Y7QUFBQSxNQUNGO0FBQUEsSUFDRjtBQUFBLEVBQ0YsQ0FBQztBQUNIOyIsCiAgIm5hbWVzIjogWyJkZWZpbmVDb25maWciLCAiZGVmaW5lQ29uZmlnIl0KfQo=
