import { useEffect, useMemo, useState } from 'react';
import { listConflicts, resolveConflicts } from '../api';
import type {
  ConflictDecision,
  ConflictGroup,
  ConflictResolution,
  ConflictResolveResponse,
} from '../types';

interface ConflictReviewModalProps {
  onClose: () => void;
  onResolved: (response: ConflictResolveResponse) => void;
}

type DecisionMap = Record<string, ConflictDecision>;

export function ConflictReviewModal({ onClose, onResolved }: ConflictReviewModalProps) {
  const [groups, setGroups] = useState<ConflictGroup[] | null>(null);
  const [decisions, setDecisions] = useState<DecisionMap>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listConflicts()
      .then((res) => {
        setGroups(res.groups);
        // Default to TRUST_SHEET to preserve the current behavior.
        const initial: DecisionMap = {};
        for (const g of res.groups) {
          initial[g.group_id] = 'TRUST_SHEET';
        }
        setDecisions(initial);
        setLoading(false);
      })
      .catch((err) => {
        setError((err as Error).message);
        setLoading(false);
      });
  }, []);

  const totalRows = useMemo(
    () => groups?.reduce((sum, g) => sum + g.rows.length, 0) ?? 0,
    [groups],
  );

  const handleDecisionChange = (groupId: string, decision: ConflictDecision) => {
    setDecisions((prev) => ({ ...prev, [groupId]: decision }));
  };

  const handleSubmit = async () => {
    if (!groups) return;
    setSubmitting(true);
    setError(null);

    const payload: ConflictResolution[] = [];
    for (const group of groups) {
      const decision = decisions[group.group_id] ?? 'TRUST_SHEET';
      for (const row of group.rows) {
        payload.push({ raw_row_id: row.raw_row_id, decision });
      }
    }

    try {
      const result = await resolveConflicts(payload);
      onResolved(result);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <div>
            <h2>Conflict review</h2>
            <p className="modal-subtitle">
              These rows have a sheet name that disagrees with column A. Choose the value to trust
              for each group.
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M6 6l12 12" />
              <path d="M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className="modal-body">
          {loading && <div className="modal-empty">Loading conflicts</div>}

          {!loading && error && (
            <div className="modal-error">
              <strong>Failed to load:</strong>
              <pre>{error}</pre>
            </div>
          )}

          {!loading && !error && groups && groups.length === 0 && (
            <div className="modal-empty">No conflicts pending review.</div>
          )}

          {!loading && groups && groups.length > 0 && (
            <ul className="conflict-list">
              {groups.map((group) => {
                const current = decisions[group.group_id] ?? 'TRUST_SHEET';
                return (
                  <li key={group.group_id} className="conflict-card">
                    <div className="conflict-header">
                      <strong>{group.sheet_name}</strong>
                      <span className="conflict-rows">{group.rows.length} rows</span>
                    </div>

                    <div className="conflict-versus">
                      <div className="versus-side">
                        <span className="versus-label">Sheet</span>
                        <span className="versus-value">{group.sheet_name}</span>
                        <span className="versus-arrow" aria-hidden="true">
                          <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M5 12h14" />
                            <path d="M13 6l6 6-6 6" />
                          </svg>
                        </span>
                        <span className="versus-sector">{group.sheet_sector_code ?? '—'}</span>
                      </div>
                      <div className="versus-side">
                        <span className="versus-label">Column A</span>
                        <span className="versus-value">{group.a_column_value ?? '—'}</span>
                        <span className="versus-arrow" aria-hidden="true">
                          <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M5 12h14" />
                            <path d="M13 6l6 6-6 6" />
                          </svg>
                        </span>
                        <span className="versus-sector">
                          {group.a_column_sector_code ?? 'Unresolved'}
                        </span>
                      </div>
                    </div>

                    <div className="conflict-rows-list">
                      Affected rows:&nbsp;
                      {group.rows
                        .slice(0, 12)
                        .map((r) => `R${r.excel_row_number}`)
                        .join(', ')}
                      {group.rows.length > 12 && ` and ${group.rows.length - 12} more`}
                    </div>

                    <div className="decision-row">
                      <label className={`decision ${current === 'TRUST_SHEET' ? 'active' : ''}`}>
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'TRUST_SHEET'}
                          onChange={() => handleDecisionChange(group.group_id, 'TRUST_SHEET')}
                          disabled={!group.sheet_sector_code}
                        />
                        <span>Trust sheet ({group.sheet_sector_code ?? '—'})</span>
                      </label>
                      <label className={`decision ${current === 'TRUST_A' ? 'active' : ''}`}>
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'TRUST_A'}
                          onChange={() => handleDecisionChange(group.group_id, 'TRUST_A')}
                          disabled={!group.a_column_sector_code}
                        />
                        <span>Trust column A ({group.a_column_sector_code ?? 'unavailable'})</span>
                      </label>
                      <label className={`decision ${current === 'SKIP' ? 'active skip' : ''}`}>
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'SKIP'}
                          onChange={() => handleDecisionChange(group.group_id, 'SKIP')}
                        />
                        <span>Skip (do not import)</span>
                      </label>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="modal-footer">
          <span className="modal-meta">
            {groups?.length ?? 0} groups &middot; {totalRows} rows pending
          </span>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
              Later
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSubmit}
              disabled={submitting || loading || !groups || groups.length === 0 || error !== null}
            >
              {submitting ? 'Applying' : `Apply decisions (${totalRows} rows)`}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
