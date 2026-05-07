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
        // 默认选 TRUST_SHEET（保持当前默认行为，最保险）
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
            <h2>冲突复核</h2>
            <p className="modal-subtitle">
              系统在 sheet 名与 A 列内容冲突的行上暂停了导入。请逐组决定使用哪边。
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ✕
          </button>
        </header>

        <div className="modal-body">
          {loading && <div className="modal-empty">加载中…</div>}

          {!loading && error && (
            <div className="modal-error">
              <strong>加载失败：</strong>
              <pre>{error}</pre>
            </div>
          )}

          {!loading && !error && groups && groups.length === 0 && (
            <div className="modal-empty">当前没有待复核的冲突 ✓</div>
          )}

          {!loading && groups && groups.length > 0 && (
            <ul className="conflict-list">
              {groups.map((group) => {
                const current = decisions[group.group_id] ?? 'TRUST_SHEET';
                return (
                  <li key={group.group_id} className="conflict-card">
                    <div className="conflict-header">
                      <strong>{group.sheet_name}</strong>
                      <span className="conflict-rows">{group.rows.length} 行</span>
                    </div>

                    <div className="conflict-versus">
                      <div className="versus-side">
                        <span className="versus-label">Sheet 名</span>
                        <span className="versus-value">{group.sheet_name}</span>
                        <span className="versus-arrow">→</span>
                        <span className="versus-sector">
                          {group.sheet_sector_code ?? '—'}
                        </span>
                      </div>
                      <div className="versus-side">
                        <span className="versus-label">A 列</span>
                        <span className="versus-value">
                          {group.a_column_value ?? '—'}
                        </span>
                        <span className="versus-arrow">→</span>
                        <span className="versus-sector">
                          {group.a_column_sector_code ?? '无法解析'}
                        </span>
                      </div>
                    </div>

                    <div className="conflict-rows-list">
                      影响行号：
                      {group.rows
                        .slice(0, 12)
                        .map((r) => `R${r.excel_row_number}`)
                        .join(', ')}
                      {group.rows.length > 12 && ` … 等 ${group.rows.length} 行`}
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
                          信 sheet（{group.sheet_sector_code ?? '—'}）
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
                          信 A 列（{group.a_column_sector_code ?? '不可用'}）
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
                        <span>跳过（不导入）</span>
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
            共 {groups?.length ?? 0} 组 · {totalRows} 行待处理
          </span>
          <div className="modal-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={submitting}
            >
              稍后再说
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
              {submitting ? '提交中…' : `应用决定（${totalRows} 行）`}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
