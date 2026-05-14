/**
 * Tests for TechnologyDetailPanel — the right-side detail pane in the Browse step.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  getTechnology: vi.fn(),
}));

import { getTechnology } from '../api';
import { TechnologyDetailPanel } from '../components/TechnologyDetailPanel';
import type { TechnologyDetail } from '../types';

const mockDetail: TechnologyDetail = {
  technology_id:              1,
  technology_code:            'COAL_PP',
  technology_description:     'Coal power plant',
  sector_code:                'ELEC',
  sector_name:                'Electricity',
  geography_code:             'SGP',
  technology_start_year:      2020,
  technology_lifetime_years:  30,
  grade:                      'A',
  years: [
    {
      technology_year_id: 10,
      data_year:          2020,
      raw_row_id:         null,
      emission_factor:    '0.85',
      emission_factor_unit: 'tCO2/MWh',
      base_currency:      'USD',
      capex:              '1200',
      capex_unit:         'USD/kW',
      fixed_opex:         '30',
      fixed_opex_unit:    'USD/kW/yr',
      variable_opex:      '5',
      variable_opex_unit: 'USD/MWh',
      tax_cost:           null,
      subsidy_cost:       null,
      efficiency_value:   '0.38',
      efficiency_text:    '38%',
      efficiency_unit:    '%',
      technology_efficiency: null,
      capacity_to_activity_factor: null,
      heat_rate:          null,
      capacity_value:     null,
      capacity_bound_type: null,
      constraint_details: [],
      commodities:        [],
    },
  ],
};

beforeEach(() => {
  vi.mocked(getTechnology).mockResolvedValue(mockDetail);
});

describe('TechnologyDetailPanel', () => {
  it('shows a placeholder message when no technology is selected (technologyId = null)', () => {
    render(<TechnologyDetailPanel technologyId={null} />);
    expect(screen.getByText(/select a technology from the list/i)).toBeInTheDocument();
  });

  it('shows a loading indicator while fetching', async () => {
    vi.mocked(getTechnology).mockImplementation(() => new Promise(() => {}));
    render(<TechnologyDetailPanel technologyId={1} />);
    expect(screen.getByText(/loading technology details/i)).toBeInTheDocument();
  });

  it('calls getTechnology with the provided ID', async () => {
    render(<TechnologyDetailPanel technologyId={42} />);
    await waitFor(() => expect(vi.mocked(getTechnology)).toHaveBeenCalledWith(42));
  });

  it('renders the technology code and description after load', async () => {
    render(<TechnologyDetailPanel technologyId={1} />);
    await waitFor(() => expect(screen.getByText('COAL_PP')).toBeInTheDocument());
    expect(screen.getByText('Coal power plant')).toBeInTheDocument();
  });

  it('renders sector name and geography code tags', async () => {
    render(<TechnologyDetailPanel technologyId={1} />);
    await waitFor(() => screen.getByText('COAL_PP'));
    expect(screen.getByText('Electricity')).toBeInTheDocument();
    expect(screen.getByText('SGP')).toBeInTheDocument();
  });

  it('shows an error message when the API call fails', async () => {
    vi.mocked(getTechnology).mockRejectedValueOnce(new Error('Not found'));
    render(<TechnologyDetailPanel technologyId={99} />);
    // Error div renders "Unable to load this technology. Not found" as one text node
    await waitFor(() =>
      expect(screen.getByText(/unable to load this technology/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/not found/i)).toBeInTheDocument();
  });

  it('renders the year data row with the data year', async () => {
    render(<TechnologyDetailPanel technologyId={1} />);
    await waitFor(() => screen.getByText('COAL_PP'));
    // 2020 appears in the start_year <dd> AND the year-table <td> row
    expect(screen.getAllByText('2020').length).toBeGreaterThanOrEqual(1);
  });

  it('re-fetches when technologyId changes', async () => {
    const { rerender } = render(<TechnologyDetailPanel technologyId={1} />);
    await waitFor(() => screen.getByText('COAL_PP'));
    rerender(<TechnologyDetailPanel technologyId={2} />);
    await waitFor(() =>
      expect(vi.mocked(getTechnology)).toHaveBeenCalledWith(2),
    );
  });

  it('resets to placeholder when technologyId changes to null', async () => {
    const { rerender } = render(<TechnologyDetailPanel technologyId={1} />);
    await waitFor(() => screen.getByText('COAL_PP'));
    rerender(<TechnologyDetailPanel technologyId={null} />);
    expect(screen.getByText(/select a technology from the list/i)).toBeInTheDocument();
  });
});
