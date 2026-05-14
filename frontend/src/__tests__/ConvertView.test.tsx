/**
 * Tests for ConvertView — the VT-workbook-to-EcoTEA conversion step.
 *
 * All API calls are mocked so no real backend is required.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  listConvertModels: vi.fn(),
  convertVT: vi.fn(),
  conversionDownloadUrl: (token: string) => `/api/convert/download/${token}`,
}));

import { listConvertModels, convertVT } from '../api';
import { ConvertView } from '../components/ConvertView';
import type { ConvertModelInfo, ConvertResult } from '../types';

const models: ConvertModelInfo[] = [
  { key: 'VT_ELEC',  label: 'VT Electricity', sector: 'ELEC',  description: 'Electricity model' },
  { key: 'VT_TRANS', label: 'VT Transport',    sector: 'TRANS', description: null },
];

const mockResult: ConvertResult = {
  download_token: 'tok-abc123',
  download_name:  'output.xlsx',
  row_count:       50,
  sheet_name:      'ELEC',
  model_key:       'VT_ELEC',
  source_file_name:   'source.xlsx',
  template_file_name: 'template.xlsx',
  bytes:     20480,
  created_at: '2024-01-15T10:00:00Z',
};

/** Drop an Excel file into the first hidden file input rendered by FileUpload. */
function selectSourceFile(name = 'source.xlsx') {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['x'], name)] } });
}

beforeEach(() => {
  vi.mocked(listConvertModels).mockResolvedValue(models);
  vi.mocked(convertVT).mockResolvedValue(mockResult);
});

describe('ConvertView', () => {
  it('loads and displays available models on mount', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getAllByRole('radio').length).toBe(models.length);
    });
    expect(screen.getByRole('radio', { name: /VT_ELEC/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /VT_TRANS/i })).toBeInTheDocument();
  });

  it('pre-selects the first model on load', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    expect(screen.getByRole('radio', { name: /VT_ELEC/i })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: /VT_TRANS/i })).toHaveAttribute('aria-checked', 'false');
  });

  it('switches the selected model when a different one is clicked', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_TRANS/i }));
    fireEvent.click(screen.getByRole('radio', { name: /VT_TRANS/i }));
    expect(screen.getByRole('radio', { name: /VT_TRANS/i })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: /VT_ELEC/i })).toHaveAttribute('aria-checked', 'false');
  });

  it('shows an error banner when listConvertModels fails', async () => {
    vi.mocked(listConvertModels).mockRejectedValueOnce(new Error('Network error'));
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/unable to load model list/i)).toBeInTheDocument(),
    );
  });

  it('"Convert workbook" button is disabled before a source file is selected', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    expect(screen.getByRole('button', { name: /convert workbook/i })).toBeDisabled();
  });

  it('enables "Convert workbook" after a valid source file is selected', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile('vt_data.xlsx');
    expect(screen.getByRole('button', { name: /convert workbook/i })).not.toBeDisabled();
  });

  it('shows a spinner and "Converting" message while the API call is in-flight', async () => {
    vi.mocked(convertVT).mockImplementation(() => new Promise(() => {})); // never resolves
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile();
    fireEvent.click(screen.getByRole('button', { name: /convert workbook/i }));
    await waitFor(() => expect(screen.getByText(/converting/i)).toBeInTheDocument());
  });

  it('shows the success panel with output metadata after a successful conversion', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile();
    fireEvent.click(screen.getByRole('button', { name: /convert workbook/i }));
    await waitFor(() => expect(screen.getByText(/conversion complete/i)).toBeInTheDocument());
    expect(screen.getByText('output.xlsx')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument(); // row_count
  });

  it('calls onHandoffToImport with the result when "Send to import" is clicked', async () => {
    const handoff = vi.fn();
    render(<ConvertView onHandoffToImport={handoff} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile();
    fireEvent.click(screen.getByRole('button', { name: /convert workbook/i }));
    await waitFor(() => screen.getByText(/conversion complete/i));
    fireEvent.click(screen.getByRole('button', { name: /send to import/i }));
    expect(handoff).toHaveBeenCalledWith(mockResult);
  });

  it('shows the error panel on a conversion failure', async () => {
    vi.mocked(convertVT).mockRejectedValueOnce(new Error('Server 500'));
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile();
    fireEvent.click(screen.getByRole('button', { name: /convert workbook/i }));
    await waitFor(() => expect(screen.getByText(/conversion failed/i)).toBeInTheDocument());
    expect(screen.getByText('Server 500')).toBeInTheDocument();
  });

  it('can reset back to idle after an error via "Try again"', async () => {
    vi.mocked(convertVT).mockRejectedValueOnce(new Error('Oops'));
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    selectSourceFile();
    fireEvent.click(screen.getByRole('button', { name: /convert workbook/i }));
    await waitFor(() => screen.getByText(/conversion failed/i));
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(screen.getByRole('button', { name: /convert workbook/i })).toBeInTheDocument();
    expect(screen.queryByText(/conversion failed/i)).not.toBeInTheDocument();
  });

  it('alerts and rejects a source file with a non-Excel extension', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    // FileUpload itself rejects non-xlsx/xlsm extensions
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'report.pdf')] } });
    expect(alertSpy).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /convert workbook/i })).toBeDisabled();
    alertSpy.mockRestore();
  });

  it('shows the custom template toggle in Step 3', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    expect(
      screen.getByRole('checkbox', { name: /use a custom ecotea template/i }),
    ).toBeInTheDocument();
  });

  it('reveals a second file picker when the custom template checkbox is ticked', async () => {
    render(<ConvertView onHandoffToImport={vi.fn()} />);
    await waitFor(() => screen.getByRole('radio', { name: /VT_ELEC/i }));
    const toggle = screen.getByRole('checkbox', { name: /use a custom ecotea template/i });
    fireEvent.click(toggle);
    // There should now be two file inputs (source + template)
    const inputs = document.querySelectorAll('input[type="file"]');
    expect(inputs.length).toBe(2);
  });
});
