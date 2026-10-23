/**
 * BarList: labelled rows, each with a bar scaled to a maximum and its value as text: a
 * screener funnel (universe -> each hard criterion), coverage by fetch-priority tier, top
 * sectors. `inline` puts label | bar | value on one line; `stacked` puts the label above the
 * bar (long labels, narrow panels). `diverging` takes signed values: bars grow right of a zero
 * axis when positive and left when negative (a return by decile), scaled to the largest
 * magnitude. Bars are decorative: each row reads as "label value". With `onSelect` each row is
 * a toggle button, and an item's `emphasis` marks it against the selected row (the selected row,
 * what it follows, what follows it, or neither: dimmed); a `hollow` item has a dashed empty track
 * (nothing was measured for it).
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
  /** This row against the selected one: itself, what it follows, what follows it, or neither. */
  emphasis?: 'selected' | 'upstream' | 'downstream' | 'dimmed';
  /** No bar at all: a dashed, empty track (the item was never measured). */
  hollow?: boolean;
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
  /** Bar colour for every row (default `accent`; a `diverging` list's rows are positive or negative). */
  tone?: DataTone;
  /** Signed values around a zero axis, scaled to the largest magnitude (`max`: the magnitude of a full half). */
  diverging?: boolean;
  loading?: boolean;
  /** Replaces the rows with this message. */
  error?: ReactNode;
  emptyMessage?: ReactNode;
  /** Makes each row a toggle button that reports its id; `aria-pressed` follows `emphasis`. */
  onSelect?: (id: string) => void;
}

export function BarList({
  items,
  label,
  max,
  format = { kind: 'number' },
  layout = 'inline',
  tone,
  diverging = false,
  loading = false,
  error,
  emptyMessage = 'No data',
  onSelect,
}: BarListProps) {
  if (error !== undefined && error !== null && error !== false) {
    return (
      <p className={styles.message} data-tone="negative" role="alert">
        {error}
      </p>
    );
  }
  if (!loading && items.length === 0) return <p className={styles.message}>{emptyMessage}</p>;
  const top = Math.max(max ?? 0, ...items.map((i) => (diverging ? Math.abs(i.value) : i.value)), 0);
  return (
    <ul
      className={styles.list}
      data-layout={layout}
      data-diverging={diverging || undefined}
      data-selectable={onSelect !== undefined || undefined}
      aria-label={label}
      aria-busy={loading || undefined}
    >
      {items.map((item) => {
        const size = diverging ? Math.abs(item.value) : Math.max(0, item.value);
        const share = top > 0 ? size / top : 0;
        // A non-zero value always shows at least a sliver of bar (a diverging half is half the track).
        const width = size > 0 ? Math.max(share, 0.01) / (diverging ? 2 : 1) : 0;
        const sign = item.value < 0 ? 'negative' : 'positive';
        const fill = item.tone ?? tone ?? (diverging ? sign : 'accent');
        const content = (
          <>
            <span className={styles.label}>{item.label}</span>
            <span
              className={styles.track}
              data-hollow={item.hollow || undefined}
              aria-hidden="true"
            >
              {!loading && !item.hollow && (
                <span
                  className={`${styles.fill} ${toneStyles.tone}`}
                  data-tone={fill}
                  data-sign={diverging ? sign : undefined}
                  style={{ '--share': `${Number((width * 100).toFixed(3))}%` } as CSSProperties}
                />
              )}
            </span>
            <span className={styles.value}>
              {loading ? null : (item.display ?? formatValue(item.value, format).text)}
            </span>
          </>
        );
        return (
          <li key={item.id} className={styles.row} data-emphasis={item.emphasis}>
            {onSelect === undefined ? (
              content
            ) : (
              <button
                type="button"
                className={styles.press}
                aria-pressed={item.emphasis === 'selected'}
                onClick={() => {
                  onSelect(item.id);
                }}
              >
                {content}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
