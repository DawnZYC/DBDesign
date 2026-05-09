import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

// Vitest reuses the existing Vite plugin pipeline (React, etc.) and adds the
// jsdom environment plus the global jest-dom matchers via setupFiles.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      css: true,
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov', 'html'],
        reportsDirectory: './coverage',
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/**/*.d.ts',
          'src/main.tsx',
          'src/types.ts',
          'src/__tests__/**',
          'src/test/**',
        ],
      },
    },
  }),
);
