/**
 * StackedBar: one bar split into toned segments that add up to a whole (option chains: OK,
 * stale, no chain, errors), with a Legend of each segment's count underneath. The bar is an
 * image whose accessible name lists every segment with its count and share; the legend repeats
 * them as text, so colour is never the only key.
 */
import type { CSSProperties, ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import { type DataTone, Legend, toneStyles } from '../Legend';
import styles from './StackedBar.module.css';

export interface StackedBarSegment {
  id: string;
  label: string;
  /** Size of the segment (a count); zero-sized segments stay in the legend only. */
  value: number;
  tone: DataTone;
}

export interface StackedBarProps {
  segments: readonly StackedBarSegment[];
  /** What the bar measures, e.g. "Option chains, Fri 2 Oct". Names the image. */
  label: string;
  /** The whole (default: the sum of the segments). A larger total leaves the rest as track. */
  total?: number;
  /** Format of the counts in the legend and the accessible name (default grouped number). */
  format?: ValueFormat;
  /** Show the legend under the bar (default true). */
  showLegend?: boolean;
  /** Bar thickness: `md` 10 px (default) or `sm` 6 px. */
  size?: 'sm' | 'md';
  /** Placeholder track while loading. */
  loading?: boolean;
  /** Replaces the bar with this message. */
  error?: ReactNode;
  /** Shown under an empty track when the total is zero. */
  emptyMessage?: ReactNode;
}

export function StackedBar({
  segments,
  label,
  total,
  format = { kind: 'number' },
  showLegend = true,
  size = 'md',
  loading = false,
  error,
  emptyMessage = 'No data',
}: StackedBarProps) {
  if (error !== undefined && error !== null && error !== false) {
    return (
      <p className={styles.message} data-tone="negative" role="alert">
        {error}
      </p>
    );
  }
  const sum = segments.reduce((acc, s) => acc + Math.max(0, s.value), 0);
  const whole = Math.max(total ?? sum, sum);
  const share = (value: number) => (whole > 0 ? Math.max(0, value) / whole : 0);
  const description = segments
    .map(
      (s) =>
        `${s.label} ${formatValue(s.value, format).text} (${formatValue(share(s.value), { kind: 'percent' }).text})`,
    )
    .join(', ');
  const empty = !loading && whole === 0;
  return (
    <div className={styles.root}>
      <div
        className={styles.track}
        data-size={size}
        role="img"
        aria-label={
          loading ? `${label}: loading` : empty ? `${label}: no data` : `${label}: ${description}`
        }
        aria-busy={loading || undefined}
      >
        {!loading &&
          segments
            .filter((s) => s.value > 0)
            .map((s) => (
              <span
                key={s.id}
                className={`${styles.segment} ${toneStyles.tone}`}
                data-tone={s.tone}
                style={{ '--share': `${share(s.value) * 100}%` } as CSSProperties}
              />
            ))}
      </div>
      {empty ? (
        <p className={styles.message}>{emptyMessage}</p>
      ) : (
        showLegend &&
        !loading && (
          <Legend
            label={label}
            items={segments.map((s) => ({
              id: s.id,
              label: s.label,
              tone: s.tone,
              value: formatValue(s.value, format).text,
            }))}
          />
        )
      )}
    </div>
  );
}
