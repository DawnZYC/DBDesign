import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteRagDocument, listRagDocuments, ragSearch, uploadRagDocument } from '../api';
import type { RagDocumentInfo, RagSearchHit } from '../api';

/**
 * KnowledgePanel — RAG knowledge-base management overlay.
 *
 * Features: upload .md/.txt documents (H2 chunking; same name overwrites),
 * list uploaded documents (chunk count + titles) with delete, and a search
 * box hitting /api/rag/search to verify the knowledge is retrievable.
 */
interface KnowledgePanelProps {
  onClose: () => void;
}

export function KnowledgePanel({ onClose }: KnowledgePanelProps) {
  const [docs, setDocs] = useState<RagDocumentInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<RagSearchHit[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocs(await listRagDocuments());
    } catch (err) {
      setNotice(`Failed to load documents: ${(err as Error).message}`);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleUpload = async (file: File) => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await uploadRagDocument(file);
      setNotice(`Ingested ${result.file} (${result.chunks} chunks)`);
      await refresh();
    } catch (err) {
      setNotice(`Upload failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (fileName: string) => {
    if (!window.confirm(`Delete all chunks of ${fileName}?`)) return;
    setBusy(true);
    try {
      await deleteRagDocument(fileName);
      setNotice(`Deleted ${fileName}`);
      await refresh();
    } catch (err) {
      setNotice(`Delete failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    try {
      setHits(await ragSearch(q, 3));
    } catch (err) {
      setNotice(`Search failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="kp-overlay" role="dialog" aria-modal="true" aria-label="Knowledge base">
      <div className="kp-panel">
        <header className="kp-header">
          <strong>Knowledge base</strong>
          <button type="button" className="kp-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <section className="kp-section">
          <div className="kp-section-title">Upload a document</div>
          <p className="kp-hint">
            Accepts .md / .txt (≤2MB). Markdown is chunked by <code>##</code> headings; plain text
            by paragraphs. Re-uploading the same file name overwrites it.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.markdown,.txt"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUpload(f);
            }}
          />
        </section>

        <section className="kp-section">
          <div className="kp-section-title">Uploaded documents ({docs.length})</div>
          {docs.length === 0 && (
            <p className="kp-hint">
              No uploads yet. Built-in knowledge (dictionary + domain handbook) is not listed here.
            </p>
          )}
          <ul className="kp-doc-list">
            {docs.map((d) => (
              <li key={d.file} className="kp-doc-item">
                <div>
                  <strong>{d.file}</strong>
                  <span className="kp-doc-meta">{d.chunks} chunks</span>
                  {d.titles.length > 0 && (
                    <div className="kp-doc-titles">{d.titles.join(' · ')}</div>
                  )}
                </div>
                <button
                  type="button"
                  className="kp-delete"
                  disabled={busy}
                  onClick={() => void handleDelete(d.file)}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="kp-section">
          <div className="kp-section-title">Search test</div>
          <div className="kp-search-row">
            <input
              type="text"
              value={query}
              placeholder='e.g. "what does grade 90 mean"'
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleSearch();
              }}
            />
            <button
              type="button"
              disabled={busy || !query.trim()}
              onClick={() => void handleSearch()}
            >
              Search
            </button>
          </div>
          {hits && (
            <ul className="kp-hit-list">
              {hits.length === 0 && <li className="kp-hint">No hits.</li>}
              {hits.map((h, i) => (
                <li key={i} className="kp-hit-item">
                  <span className="kp-hit-score">{h.score.toFixed(3)}</span>
                  <span className="kp-hit-source">{String(h.metadata.source ?? '')}</span>
                  <div className="kp-hit-text">{h.text.slice(0, 160)}…</div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {notice && <div className="kp-notice">{notice}</div>}
      </div>
    </div>
  );
}
