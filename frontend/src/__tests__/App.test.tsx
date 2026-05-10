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
}));

import App from '../App';

describe('App', () => {
  it('renders the EcoTEA header and both navigation tabs', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: /EcoTEA WP1/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Import Data/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Browse Data/i })).toBeInTheDocument();
  });

  it('reports an online status once the health check resolves', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Online/i)).toBeInTheDocument());
  });
});
