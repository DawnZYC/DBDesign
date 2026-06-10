import { useEffect, useState } from 'react';
import type {
  ColumnOverrides,
  SheetColumnMapping,
  StandardFieldInfo,
} from '../types';

/**
 * M5 列对齐复核（导入前）。
 *
 * 当某 sheet 的表头与标准模板不一致（SG-TIMES 版本迭代导致列布局变化）时，
 * Schema-Mapping Agent 给出每列的匹配建议与置信度：
 *   - auto（≥0.9）：已自动对齐，可改
 *   - review（0.6-0.9）：低置信，需人工确认
 *   - unmatched（<0.6）：默认不导入，可手动指定
 * 用户确认后产出 columnOverrides（{sheet: {陌生列: 标准列}}）回传导入接口。
 */
interface ColumnMappingReviewProps {
  mappings: SheetColumnMapping[]; // 只传 layout_is_standard=false 的 sheet
  standardFields: StandardFieldInfo[];
  onChange: (overrides: ColumnOverrides) => void;
}

const NONE = '__none__'; // 下拉里「不导入此列」的占位值

export function ColumnMappingReview({
  mappings,
  standardFields,
  onChange,
}: ColumnMappingReviewProps) {
  // 每个 (sheet, excel_column) 当前选定的标准列；'' / NONE 表示不导入
  const [choice, setChoice] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const m of mappings) {
      for (const s of m.suggestions) {
        const key = `${m.sheet_name}::${s.excel_column}`;
        // auto / review 预填建议的标准列；unmatched 默认不导入
        init[key] =
          s.status !== 'unmatched' && s.target_column ? s.target_column : NONE;
      }
    }
    return init;
  });

  // 把 choice 折叠成 overrides 上抛
  useEffect(() => {
    const overrides: ColumnOverrides = {};
    for (const m of mappings) {
      const sheetMap: Record<string, string> = {};
      const usedTargets = new Set<string>();
      for (const s of m.suggestions) {
        const key = `${m.sheet_name}::${s.excel_column}`;
        const target = choice[key];
        if (target && target !== NONE && !usedTargets.has(target)) {
          sheetMap[s.excel_column] = target;
          usedTargets.add(target);
        }
      }
      if (Object.keys(sheetMap).length > 0) overrides[m.sheet_name] = sheetMap;
    }
    onChange(overrides);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choice]);

  if (mappings.length === 0) return null;

  const totalReview = mappings.reduce((n, m) => n + m.review_count, 0);

  return (
    <section className="column-mapping-review">
      <header className="cmr-header">
        <strong>列对齐复核</strong>
        <span className="cmr-hint">
          检测到 {mappings.length} 个 sheet 的列布局与标准模板不一致
          {totalReview > 0 ? `，其中 ${totalReview} 列置信度偏低，请确认` : ''}
          。Schema-Mapping Agent 已给出建议，可逐列调整。
        </span>
      </header>

      {mappings.map((m) => (
        <div key={m.sheet_name} className="cmr-sheet">
          <div className="cmr-sheet-title">
            {m.sheet_name}
            <span className="cmr-badge cmr-auto">{m.auto_count} 自动</span>
            {m.review_count > 0 && (
              <span className="cmr-badge cmr-review">{m.review_count} 待确认</span>
            )}
            {m.unmatched_count > 0 && (
              <span className="cmr-badge cmr-unmatched">
                {m.unmatched_count} 未匹配
              </span>
            )}
          </div>

          <table className="cmr-table">
            <thead>
              <tr>
                <th>源列</th>
                <th>表头原文</th>
                <th>对齐到标准字段</th>
                <th>置信度</th>
              </tr>
            </thead>
            <tbody>
              {m.suggestions.map((s) => {
                const key = `${m.sheet_name}::${s.excel_column}`;
                const selected = choice[key] ?? NONE;
                return (
                  <tr key={key} className={`cmr-row cmr-${s.status}`}>
                    <td className="cmr-col">{s.excel_column}</td>
                    <td className="cmr-srchdr" title={s.reasoning}>
                      {s.excel_header || <em>（空）</em>}
                    </td>
                    <td>
                      <select
                        value={selected}
                        onChange={(e) =>
                          setChoice((prev) => ({ ...prev, [key]: e.target.value }))
                        }
                      >
                        <option value={NONE}>— 不导入此列 —</option>
                        {standardFields.map((f) => (
                          <option key={f.column} value={f.column}>
                            {f.column} · {f.label} ({f.field})
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="cmr-conf">
                      {s.target_field ? `${Math.round(s.confidence * 100)}%` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
