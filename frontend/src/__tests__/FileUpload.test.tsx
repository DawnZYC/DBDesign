import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileUpload } from '../components/FileUpload';

const makeFile = (name: string, content = 'data') =>
  new File([content], name, { type: 'application/octet-stream' });

describe('FileUpload', () => {
  it('renders the drop zone with accessible label and hint text', () => {
    render(<FileUpload onFileSelected={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: /select or drop an excel file/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/click to choose a file/i)).toBeInTheDocument();
    expect(screen.getByText(/\.xlsx or \.xlsm/i)).toBeInTheDocument();
  });

  it('calls onFileSelected with a valid .xlsx file chosen via the input', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile('import.xlsx');
    fireEvent.change(input, { target: { files: [file] } });
    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith(file);
  });

  it('calls onFileSelected with a valid .xlsm file chosen via the input', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile('macro.xlsm');
    fireEvent.change(input, { target: { files: [file] } });
    expect(handler).toHaveBeenCalledWith(file);
  });

  it('fires an alert and skips the callback for an unsupported file extension', () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [makeFile('document.pdf')] } });
    expect(alertSpy).toHaveBeenCalledOnce();
    expect(handler).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('adds drag-over class while dragging over the zone', () => {
    render(<FileUpload onFileSelected={vi.fn()} />);
    const zone = screen.getByRole('button', { name: /select or drop/i });
    fireEvent.dragOver(zone);
    expect(zone).toHaveClass('drag-over');
  });

  it('removes drag-over class on drag-leave', () => {
    render(<FileUpload onFileSelected={vi.fn()} />);
    const zone = screen.getByRole('button', { name: /select or drop/i });
    fireEvent.dragOver(zone);
    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass('drag-over');
  });

  it('calls onFileSelected when a valid file is dropped', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} />);
    const zone = screen.getByRole('button', { name: /select or drop/i });
    const file = makeFile('dropped.xlsx');
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(handler).toHaveBeenCalledWith(file);
  });

  it('ignores a dropped file when disabled', () => {
    const handler = vi.fn();
    render(<FileUpload onFileSelected={handler} disabled />);
    const zone = screen.getByRole('button', { name: /select or drop/i });
    fireEvent.drop(zone, { dataTransfer: { files: [makeFile('file.xlsx')] } });
    expect(handler).not.toHaveBeenCalled();
  });

  it('does not set drag-over class when disabled and dragging over', () => {
    render(<FileUpload onFileSelected={vi.fn()} disabled />);
    const zone = screen.getByRole('button', { name: /select or drop/i });
    fireEvent.dragOver(zone);
    expect(zone).not.toHaveClass('drag-over');
  });

  it('applies the disabled CSS class when the disabled prop is true', () => {
    render(<FileUpload onFileSelected={vi.fn()} disabled />);
    expect(screen.getByRole('button', { name: /select or drop/i })).toHaveClass('disabled');
  });
});
