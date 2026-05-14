/**
 * Tests for TechnologyList — the Browse step's filterable technology list with pagination.
 */
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  listSectors:      vi.fn(),
  listGeographies:  vi.fn(),
  listTechnologies: vi.fn(),
}));

import { listSectors, listGeographies, listTechnologies } from '../api';
import { TechnologyList } from '../components/TechnologyList';
import type { Sector, Geography, TechnologyListResponse } from '../types';

const sectors: Sector[] = [
  { sector_id: 1, sector_code: 'ELEC',  sector_name: 'Electricity' },
  { sector_id: 2, sector_code: 'TRANS', sector_name: 'Transport' },
];

const geographies: Geography[] = [
  { geography_id: 1, geography_code: 'SGP', geography_name: 'Singapore' },
  { geography_id: 2, geography_code: 'MYS', geography_name: 'Malaysia' },
];

const makeTechResponse = (total = 1): TechnologyListResponse => ({
  items: Array.from({ length: Math.min(total, 20) }, (_, i) => ({
    technology_id:           i + 1,
    technology_code:         `TECH_${i + 1}`,
    technology_description:  `Technology ${i + 1}`,
    sector_code:             'ELEC',
    sector_name:             'Electricity',
    geography_code:          'SGP',
    technology_start_year:   2020,
    technology_lifetime_years: 25,
    grade:                   'A',
    year_count:              5,
    year_min:                2020,
    year_max:                2024,
  })),
  total,
  page: 1,
  page_size: 20,
});

beforeEach(() => {
  vi.mocked(listSectors).mockResolvedValue(sectors);
  vi.mocked(listGeographies).mockResolvedValue(geographies);
  vi.mocked(listTechnologies).mockResolvedValue(makeTechResponse());
});

describe('TechnologyList', () => {
  it('shows a loading indicator before data arrives', () => {
    vi.mocked(listTechnologies).mockImplementation(() => new Promise(() => {}));
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    expect(screen.getByText(/loading technologies/i)).toBeInTheDocument();
  });

  it('renders technology cards after data loads', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => expect(screen.getByText('TECH_1')).toBeInTheDocument());
  });

  it('shows "1 technology" count in the panel header', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => expect(screen.getByText(/1 technology/i)).toBeInTheDocument());
  });

  it('shows "N technologies" in plural for multiple results', async () => {
    vi.mocked(listTechnologies).mockResolvedValue(makeTechResponse(3));
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => expect(screen.getByText(/3 technologies/i)).toBeInTheDocument());
  });

  it('shows an empty-state message when no technologies match', async () => {
    vi.mocked(listTechnologies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() =>
      expect(screen.getByText(/no technologies match/i)).toBeInTheDocument(),
    );
  });

  it('shows an error message when the API call fails', async () => {
    vi.mocked(listTechnologies).mockRejectedValueOnce(new Error('Timeout'));
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() =>
      expect(screen.getByText(/unable to load technologies/i)).toBeInTheDocument(),
    );
  });

  it('populates the sector dropdown with options from the API', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const sectorSelect = screen.getByRole('combobox', { name: /filter by sector/i });
    expect(within(sectorSelect).getByRole('option', { name: /electricity/i })).toBeInTheDocument();
    expect(within(sectorSelect).getByRole('option', { name: /transport/i })).toBeInTheDocument();
  });

  it('populates the geography dropdown with options from the API', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const geoSelect = screen.getByRole('combobox', { name: /filter by geography/i });
    // Component renders geography_code ('SGP', 'MYS'), not geography_name
    expect(within(geoSelect).getByRole('option', { name: /SGP/i })).toBeInTheDocument();
    expect(within(geoSelect).getByRole('option', { name: /MYS/i })).toBeInTheDocument();
  });

  it('re-fetches technologies when the sector filter changes', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const sectorSelect = screen.getByRole('combobox', { name: /filter by sector/i });
    fireEvent.change(sectorSelect, { target: { value: '1' } });
    await waitFor(() =>
      expect(vi.mocked(listTechnologies)).toHaveBeenCalledWith(
        expect.objectContaining({ sector_id: 1 }),
      ),
    );
  });

  it('re-fetches when the geography filter changes', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const geoSelect = screen.getByRole('combobox', { name: /filter by geography/i });
    fireEvent.change(geoSelect, { target: { value: '2' } });
    await waitFor(() =>
      expect(vi.mocked(listTechnologies)).toHaveBeenCalledWith(
        expect.objectContaining({ geography_id: 2 }),
      ),
    );
  });

  it('re-fetches with a search term when the search input changes', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const searchInput = screen.getByRole('textbox', { name: /search technologies/i });
    fireEvent.change(searchInput, { target: { value: 'coal' } });
    await waitFor(() =>
      expect(vi.mocked(listTechnologies)).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'coal' }),
      ),
    );
  });

  it('calls onSelect with the technology ID when a card is clicked', async () => {
    const onSelect = vi.fn();
    render(<TechnologyList onSelect={onSelect} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    fireEvent.click(screen.getByText('TECH_1'));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('marks the selected card with the "selected" CSS class', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={1} />);
    await waitFor(() => screen.getByText('TECH_1'));
    const card = screen.getByText('TECH_1').closest('li');
    expect(card).toHaveClass('selected');
  });

  it('shows Next/Previous pagination buttons', async () => {
    vi.mocked(listTechnologies).mockResolvedValue({ ...makeTechResponse(40), total: 40 });
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
  });

  it('disables the Previous button on page 1', async () => {
    render(<TechnologyList onSelect={vi.fn()} selectedId={null} />);
    await waitFor(() => screen.getByText('TECH_1'));
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
  });
});
