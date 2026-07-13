/**
 * EmissionFactorView — manual EF entry tests.
 *
 * TechnologyList and the api layer are mocked; tests drive the per-year edit
 * table (dirty tracking, save, clear, validation) and the add-a-year form.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EmissionFactorView } from '../components/EmissionFactorView';

const mocks = vi.hoisted(() => ({
  getTechnology: vi.fn(),
  upsertEmissionFactor: vi.fn(),
}));

vi.mock('../api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../api')>();
  return { ...mod, ...mocks };
});

// TechnologyList has its own suite; replace it with a picker stub.
vi.mock('../components/TechnologyList', () => ({
  TechnologyList: ({ onSelect }: { onSelect: (id: number) => void }) => (
    <button type="button" onClick={() => onSelect(7)}>
      pick-tech-7
    </button>
  ),
}));

const detail = {
  technology_id: 7,
  technology_code: 'PWR-COAL-01',
  technology_description: 'Coal plant',
  sector_name: 'Power',
  geography_code: 'SG',
  years: [
    { data_year: 2035, emission_factor: null, emission_factor_unit: null },
    { data_year: 2030, emission_factor: '0.85', emission_factor_unit: 'kt-CO2/PJ' },
  ],
};

beforeEach(() => {
  mocks.getTechnology.mockResolvedValue(detail);
});

afterEach(() => {
  vi.clearAllMocks();
});

async function renderWithTech() {
  render(<EmissionFactorView />);
  fireEvent.click(screen.getByText('pick-tech-7'));
  await screen.findByText('PWR-COAL-01');
}

describe('EmissionFactorView', () => {
  it('prompts to select a technology initially', () => {
    render(<EmissionFactorView />);
    expect(screen.getByText(/Select a technology/)).toBeInTheDocument();
  });

  it('loads the technology and lists its years sorted ascending', async () => {
    await renderWithTech();
    expect(screen.getByText(/Coal plant/)).toBeInTheDocument();
    const rows = screen.getAllByRole('row').slice(1); // skip thead
    expect(rows[0]).toHaveTextContent('2030');
    expect(rows[1]).toHaveTextContent('2035');
    expect(screen.getByLabelText('Emission factor for 2030')).toHaveValue('0.85');
  });

  it('shows a load error when the fetch fails', async () => {
    mocks.getTechnology.mockRejectedValue(new Error('boom'));
    render(<EmissionFactorView />);
    fireEvent.click(screen.getByText('pick-tech-7'));
    expect(await screen.findByText(/Unable to load technology/)).toBeInTheDocument();
  });

  it('enables Save only when a row is dirty, then saves and shows Saved', async () => {
    mocks.upsertEmissionFactor.mockResolvedValue({
      emission_factor: '0.9',
      emission_factor_unit: 'kt-CO2/PJ',
    });
    await renderWithTech();

    const saveButtons = screen.getAllByText('Save');
    expect(saveButtons[0]).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Emission factor for 2030'), {
      target: { value: '0.9' },
    });
    expect(saveButtons[0]).toBeEnabled();

    fireEvent.click(saveButtons[0]);
    expect(await screen.findByText('Saved')).toBeInTheDocument();
    expect(mocks.upsertEmissionFactor).toHaveBeenCalledWith(7, {
      data_year: 2030,
      emission_factor: 0.9,
      emission_factor_unit: 'kt-CO2/PJ',
    });
  });

  it('sends null when the value is blanked (clear semantics)', async () => {
    mocks.upsertEmissionFactor.mockResolvedValue({
      emission_factor: null,
      emission_factor_unit: null,
    });
    await renderWithTech();

    fireEvent.change(screen.getByLabelText('Emission factor for 2030'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getAllByText('Save')[0]);

    await waitFor(() =>
      expect(mocks.upsertEmissionFactor).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ data_year: 2030, emission_factor: null }),
      ),
    );
  });

  it('rejects a non-numeric value without calling the API', async () => {
    await renderWithTech();
    fireEvent.change(screen.getByLabelText('Emission factor for 2030'), {
      target: { value: 'abc' },
    });
    fireEvent.click(screen.getAllByText('Save')[0]);

    expect(await screen.findByText(/Enter a number/)).toBeInTheDocument();
    expect(mocks.upsertEmissionFactor).not.toHaveBeenCalled();
  });

  it('surfaces backend save errors on the row', async () => {
    mocks.upsertEmissionFactor.mockRejectedValue(new Error('Failed to save the emission factor.'));
    await renderWithTech();

    fireEvent.change(screen.getByLabelText('Emission factor for 2030'), {
      target: { value: '1.1' },
    });
    fireEvent.click(screen.getAllByText('Save')[0]);

    expect(await screen.findByText(/Failed to save/)).toBeInTheDocument();
  });

  describe('add a year', () => {
    it('validates the year range', async () => {
      await renderWithTech();
      fireEvent.change(screen.getByLabelText('New year'), { target: { value: '1500' } });
      fireEvent.click(screen.getByText('Add'));
      expect(await screen.findByText(/valid year/)).toBeInTheDocument();
      expect(mocks.upsertEmissionFactor).not.toHaveBeenCalled();
    });

    it('rejects a duplicate year', async () => {
      await renderWithTech();
      fireEvent.change(screen.getByLabelText('New year'), { target: { value: '2030' } });
      fireEvent.click(screen.getByText('Add'));
      expect(await screen.findByText(/already exists/)).toBeInTheDocument();
    });

    it('adds a new year in sorted position and clears the form', async () => {
      mocks.upsertEmissionFactor.mockResolvedValue({
        emission_factor: '0.5',
        emission_factor_unit: 'kt-CO2/PJ',
      });
      await renderWithTech();

      fireEvent.change(screen.getByLabelText('New year'), { target: { value: '2032' } });
      fireEvent.change(screen.getByLabelText('New emission factor'), {
        target: { value: '0.5' },
      });
      fireEvent.click(screen.getByText('Add'));

      await waitFor(() =>
        expect(mocks.upsertEmissionFactor).toHaveBeenCalledWith(7, {
          data_year: 2032,
          emission_factor: 0.5,
          emission_factor_unit: 'kt-CO2/PJ',
        }),
      );
      const rows = screen.getAllByRole('row').slice(1);
      expect(rows.map((r) => r.textContent?.slice(0, 4))).toEqual(['2030', '2032', '2035']);
      expect(screen.getByLabelText('New year')).toHaveValue('');
    });
  });
});
