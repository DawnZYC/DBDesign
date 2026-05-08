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
            <h2>Conflict Review</h2>
            <p className="modal-subtitle">
              Rows where the sheet name conflicts with column A were held. Choose which value to use for each group.
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="modal-body">
          {loading && <div className="modal-empty">Loading...</div>}

          {!loading && error && (
            <div className="modal-error">
              <strong>Failed to load:</strong>
              <pre>{error}</pre>
            </div>
          )}

          {!loading && !error && groups && groups.length === 0 && (
            <div className="modal-empty">No conflicts are pending review ✓</div>
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
                        <span className="versus-label">Sheet Name</span>
                        <span className="versus-value">{group.sheet_name}</span>
                        <span className="versus-arrow">→</span>
                        <span className="versus-sector">
                          {group.sheet_sector_code ?? '—'}
                        </span>
                      </div>
                      <div className="versus-side">
                        <span className="versus-label">Column A</span>
                        <span className="versus-value">
                          {group.a_column_value ?? '—'}
                        </span>
                        <span className="versus-arrow">→</span>
                        <span className="versus-sector">
                          {group.a_column_sector_code ?? 'Unresolved'}
                        </span>
                      </div>
                    </div>

                    <div className="conflict-rows-list">
                      Affected rows:
                      {group.rows
                        .slice(0, 12)
                        .map((r) => `R${r.excel_row_number}`)
                        .join(', ')}
                      {group.rows.length > 12 && ` ... ${group.rows.length} rows total`}
                    </div>

                    <div className="decision-row">
                      <label
                        className={`decision ${
                          current === 'TRUST_SHEET' ? 'active' : ''
                        }`}
                      >
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'TRUST_SHEET'}
                          onChange={() =>
                            handleDecisionChange(group.group_id, 'TRUST_SHEET')
                          }
                          disabled={!group.sheet_sector_code}
                        />
                        <span>
                          Trust sheet ({group.sheet_sector_code ?? '—'})
                        </span>
                      </label>
                      <label
                        className={`decision ${
                          current === 'TRUST_A' ? 'active' : ''
                        }`}
                      >
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'TRUST_A'}
                          onChange={() =>
                            handleDecisionChange(group.group_id, 'TRUST_A')
                          }
                          disabled={!group.a_column_sector_code}
                        />
                        <span>
                          Trust column A ({group.a_column_sector_code ?? 'unavailable'})
                        </span>
                      </label>
                      <label
                        className={`decision ${
                          current === 'SKIP' ? 'active skip' : ''
                        }`}
                      >
                        <input
                          type="radio"
                          name={group.group_id}
                          checked={current === 'SKIP'}
                          onChange={() =>
                            handleDecisionChange(group.group_id, 'SKIP')
                          }
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
            {groups?.length ?? 0} groups · {totalRows} rows pending
          </span>
          <div className="modal-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Later
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSubmit}
              disabled={
                submitting ||
                loading ||
                !groups ||
                groups.length === 0 ||
                error !== null
              }
            >
              {submitting ? 'Submitting...' : `Apply Decisions (${totalRows} rows)`}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
