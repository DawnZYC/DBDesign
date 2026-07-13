/**
 * KnowledgePanel — RAG knowledge-base overlay tests.
 *
 * The api module is mocked; tests drive upload / list / delete / search flows.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { KnowledgePanel } from '../components/KnowledgePanel';

const mocks = vi.hoisted(() => ({
  listRagDocuments: vi.fn(),
  uploadRagDocument: vi.fn(),
  deleteRagDocument: vi.fn(),
  ragSearch: vi.fn(),
}));

vi.mock('../api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../api')>();
  return { ...mod, ...mocks };
});

beforeEach(() => {
  mocks.listRagDocuments.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('KnowledgePanel', () => {
  it('lists uploaded documents with chunk counts and titles', async () => {
    mocks.listRagDocuments.mockResolvedValue([
      { file: 'notes.md', chunks: 3, titles: ['Alpha', 'Beta'] },
    ]);
    render(<KnowledgePanel onClose={() => {}} />);

    expect(await screen.findByText('notes.md')).toBeInTheDocument();
    expect(screen.getByText('3 chunks')).toBeInTheDocument();
    expect(screen.getByText('Alpha · Beta')).toBeInTheDocument();
    expect(screen.getByText('Uploaded documents (1)')).toBeInTheDocument();
  });

  it('shows the empty hint when nothing was uploaded', async () => {
    render(<KnowledgePanel onClose={() => {}} />);
    expect(await screen.findByText(/No uploads yet/)).toBeInTheDocument();
  });

  it('calls onClose from the header button', async () => {
    const onClose = vi.fn();
    render(<KnowledgePanel onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('uploads a file and reports ingested chunks', async () => {
    mocks.uploadRagDocument.mockResolvedValue({ file: 'k.md', chunks: 2 });
    const { container } = render(<KnowledgePanel onClose={() => {}} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['## A\ntext'], 'k.md', { type: 'text/markdown' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText('Ingested k.md (2 chunks)')).toBeInTheDocument();
    expect(mocks.uploadRagDocument).toHaveBeenCalledWith(file);
  });

  it('surfaces upload failures', async () => {
    mocks.uploadRagDocument.mockRejectedValue(new Error('too large'));
    const { container } = render(<KnowledgePanel onClose={() => {}} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'big.md')] } });

    expect(await screen.findByText('Upload failed: too large')).toBeInTheDocument();
  });

  it('deletes a document after confirmation', async () => {
    mocks.listRagDocuments.mockResolvedValue([{ file: 'old.md', chunks: 1, titles: [] }]);
    mocks.deleteRagDocument.mockResolvedValue({ deleted: 1 });
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<KnowledgePanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Delete'));

    await waitFor(() => expect(mocks.deleteRagDocument).toHaveBeenCalledWith('old.md'));
    expect(await screen.findByText('Deleted old.md')).toBeInTheDocument();
  });

  it('does not delete when the confirm dialog is cancelled', async () => {
    mocks.listRagDocuments.mockResolvedValue([{ file: 'keep.md', chunks: 1, titles: [] }]);
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<KnowledgePanel onClose={() => {}} />);
    fireEvent.click(await screen.findByText('Delete'));

    expect(mocks.deleteRagDocument).not.toHaveBeenCalled();
  });

  it('runs a search on Enter and renders scored hits', async () => {
    mocks.ragSearch.mockResolvedValue([
      {
        text: 'Grade 90 means the data quality tier',
        score: 0.8123,
        metadata: { source: 'manual' },
      },
    ]);
    render(<KnowledgePanel onClose={() => {}} />);

    const input = screen.getByPlaceholderText(/grade 90/);
    fireEvent.change(input, { target: { value: 'grade 90' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(await screen.findByText('0.812')).toBeInTheDocument();
    expect(screen.getByText('manual')).toBeInTheDocument();
    expect(mocks.ragSearch).toHaveBeenCalledWith('grade 90', 3);
  });

  it('renders the no-hits row for an empty result', async () => {
    mocks.ragSearch.mockResolvedValue([]);
    render(<KnowledgePanel onClose={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText(/grade 90/), { target: { value: 'zzz' } });
    fireEvent.click(screen.getByText('Search'));

    expect(await screen.findByText('No hits.')).toBeInTheDocument();
  });
});
