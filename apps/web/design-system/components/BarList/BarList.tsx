/**
 * BarList: labelled rows, each with a bar scaled to a maximum and its value as text: a
 * screener funnel (universe -> each hard criterion), coverage by fetch-priority tier, top
 * sectors. `inline` puts label | bar | value on one line; `stacked` puts the label above the
 * bar (long labels, narrow panels). Bars are decorative: each row reads as "label value".
 */
import type { CSSProperties, ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { type DataTone, toneStyles } from '../Legend';
import styles from './BarList.module.css';

export interface BarListItem {
  id: string;
  label: ReactNode;
  /** Bar length relative to `max`. */
  value: number;
  /** Text shown instead of the formatted value (e.g. `99.6%` for a share). */
  display?: ReactNode;
  /** Bar colour (default: the list's tone). */
  tone?: DataTone;
}

export interface BarListProps {
  items: readonly BarListItem[];
  /** Accessible name of the list, e.g. "Funnel (hard criteria)". */
  label: string;
  /** The value of a full-length bar (default: the largest value). A funnel passes its universe. */
  max?: number;
  /** Format of the values (default grouped number). */
  format?: ValueFormat;
  /** `inline` (label | bar | value) or `stacked` (label above bar, value at the end). */
  layout?: 'inline' | 'stacked';
  /** Bar colour for every row (default `accent`). */
  tone?: DataTone;
  loading?: boolean;
  /** Replaces the rows with this message. */
  error?: ReactNode;
  emptyMessage?: ReactNode;
}

export function BarList({
  items,
  label,
  max,
  format = { kind: 'number' },
  layout = 'inline',
  tone = 'accent',
  loading = false,
  error,
  emptyMessage = 'No data',
}: BarListProps) {
  if (error !== undefined && error !== null && error !== false) {
    return (
      <p className={styles.message} data-tone="negative" role="alert">
        {error}
      </p>
    );
  }
  if (!loading && items.length === 0) return <p className={styles.message}>{emptyMessage}</p>;
  const top = Math.max(max ?? 0, ...items.map((i) => i.value), 0);
  return (
    <ul
      className={styles.list}
      data-layout={layout}
      aria-label={label}
      aria-busy={loading || undefined}
    >
      {items.map((item) => {
        const share = top > 0 ? Math.max(0, item.value) / top : 0;
        // A non-zero value always shows at least a sliver of bar.
        const width = item.value > 0 ? Math.max(share, 0.01) : 0;
        return (
          <li key={item.id} className={styles.row}>
            <span className={styles.label}>{item.label}</span>
            <span className={styles.track} aria-hidden="true">
              {!loading && (
                <span
                  className={`${styles.fill} ${toneStyles.tone}`}
                  data-tone={item.tone ?? tone}
                  style={{ '--share': `${Number((width * 100).toFixed(3))}%` } as CSSProperties}
                />
              )}
            </span>
            <span className={styles.value}>
              {loading ? null : (item.display ?? formatValue(item.value, format).text)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
