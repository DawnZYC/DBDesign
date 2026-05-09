/**
 * Vitest setup: extend `expect` with jest-dom matchers and ensure DOM is
 * cleaned up between tests.
 */
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});
