/**
 * StatStrip: a summary row of a few headline numbers (completeness, checks, run time, open
 * issues), separated by thin borders inside one bordered strip, never as separate cards. Each
 * stat has a label, a value (text or a formatted number, optionally toned) and a sub-line. The
 * strip wraps to two columns, then one, in narrow containers. Loading shows placeholders.
 */
import type { CSSProperties, ReactNode } from 'react';

import { formatValue, type ValueFormat } from '../../format';
import styles from './StatStrip.module.css';

export interface StatItem {
  /** Stable key (defaults to the label). */
  id?: string;
  label: ReactNode;
  /** The headline value: a node, or a raw value formatted with `format`. */
  value: ReactNode;
  format?: ValueFormat;
  /** Small line under the value (context, the rule, the comparison). */
  sub?: ReactNode;
  /** Colour of the value: a status (`positive`, `warning`, `negative`), `up` / `down` or default. */
  tone?: 'default' | 'positive' | 'warning' | 'negative' | 'info' | 'up' | 'down' | 'muted';
}

export interface StatStripProps {
  items: readonly StatItem[];
  /** Accessible name of the strip, e.g. "Summary". */
  label: string;
  /** Show placeholders instead of values. */
  loading?: boolean;
  /** Replaces the values with this message (the summary failed to load). */
  error?: ReactNode;
  /** Shown when there are no items. */
  emptyMessage?: ReactNode;
}

function value(item: StatItem): { node: ReactNode; tone: string } {
  const raw = item.value;
  if (
    item.format &&
    (raw === null || raw === undefined || typeof raw === 'number' || typeof raw === 'string')
  ) {
    const formatted = formatValue(raw, item.format);
    return { node: formatted.text, tone: item.tone ?? formatted.tone };
  }
  return { node: raw, tone: item.tone ?? 'default' };
}

export function StatStrip({
  items,
  label,
  loading = false,
  error,
  emptyMessage = 'No figures yet',
}: StatStripProps) {
  const failed = error !== undefined && error !== null && error !== false;
  return (
    <section className={styles.strip} aria-label={label} aria-busy={loading || undefined}>
      {failed ? (
        <p className={styles.message} data-tone="negative" role="alert">
          {error}
        </p>
      ) : items.length === 0 && !loading ? (
        <p className={styles.message}>{emptyMessage}</p>
      ) : (
        <dl
          className={styles.list}
          style={{ '--stat-count': Math.max(items.length, 1) } as CSSProperties}
        >
          {items.map((item, index) => {
            const shown = value(item);
            return (
              <div
                key={item.id ?? (typeof item.label === 'string' ? item.label : index)}
                className={styles.stat}
              >
                <dt className={styles.label}>{item.label}</dt>
                <dd className={styles.value} data-tone={shown.tone}>
                  {loading ? (
                    <span className={styles.placeholder} aria-hidden="true" />
                  ) : (
                    shown.node
                  )}
                </dd>
                {item.sub !== undefined && (
                  <dd className={styles.sub}>{loading ? null : item.sub}</dd>
                )}
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}
