/**
 * Smoke test for the top-level <App /> component.
 *
 * The real backend is not available in CI, so we mock the api module to keep
 * the test deterministic.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
  checkHealth: vi.fn().mockResolvedValue({ status: 'ok', database: 'ok' }),
  // The other exports are not exercised by these tests but are referenced
  // transitively by child components, so provide harmless stubs.
  previewExcel: vi.fn(),
  uploadExcel: vi.fn(),
  listConflicts: vi.fn().mockResolvedValue({ groups: [] }),
  resolveConflicts: vi.fn(),
  listSectors: vi.fn().mockResolvedValue([]),
  listGeographies: vi.fn().mockResolvedValue([]),
  listTechnologies: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
  getTechnology: vi.fn(),
  listConvertModels: vi.fn().mockResolvedValue([]),
  convertVT: vi.fn(),
  conversionDownloadUrl: (token: string) => `/api/convert/download/${token}`,
  previewFromConversion: vi.fn(),
  importFromConversion: vi.fn(),
}));

import App from '../App';

describe('App', () => {
  it('renders the brand and the three workflow steps in the sidebar', () => {
    render(<App />);
    expect(screen.getByText(/EcoTEA WP1/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /01 Convert/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /02 Import/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /03 Browse/i })).toBeInTheDocument();
  });

  it('reports an online status once the health check resolves', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Online/i)).toBeInTheDocument());
  });
});
