/**
 * ShareBar: one horizontal bar showing a share of a whole (coverage 94.1%, completeness 86%),
 * with the percentage as text beside it. Exposed as a meter (`role="meter"`) with the value as
 * text, so the colour is never the only signal (an unknown or loading share is an image named
 * "<label>: unknown"). Tone defaults to the accent.
 */
import type { CSSProperties } from 'react';

import { formatValue } from '../../format';
import { type DataTone, toneStyles } from '../Legend';
import styles from './ShareBar.module.css';

export interface ShareBarProps {
  /** The share as a fraction, 0 to 1 (clamped). `null` = unknown: empty track and an em dash. */
  value: number | null;
  /** Accessible name, e.g. "S&P 500 coverage". Shown above the bar with `showLabel`. */
  label: string;
  /** Show the label above the bar (otherwise it names the meter for screen readers only). */
  showLabel?: boolean;
  /** Show the percentage after the bar (default true). */
  showValue?: boolean;
  /** Fraction digits of the percentage (default 1). */
  digits?: number;
  /** Fill colour (default `accent`). */
  tone?: DataTone;
  /** Bar thickness: `sm` 6 px (lists, default) or `md` 10 px (a headline bar). */
  size?: 'sm' | 'md';
  /** Placeholder track while the value loads. */
  loading?: boolean;
}

export function ShareBar({
  value,
  label,
  showLabel = false,
  showValue = true,
  digits = 1,
  tone = 'accent',
  size = 'sm',
  loading = false,
}: ShareBarProps) {
  const known = value !== null && !Number.isNaN(value) && !loading;
  const share = known ? Math.min(1, Math.max(0, value)) : 0;
  const text = loading ? '' : formatValue(known ? share : null, { kind: 'percent', digits }).text;
  return (
    <div className={styles.root} data-labelled={showLabel || undefined}>
      {showLabel && <span className={styles.label}>{label}</span>}
      <div
        className={styles.track}
        data-size={size}
        {...(known
          ? {
              role: 'meter',
              'aria-label': label,
              'aria-valuemin': 0,
              'aria-valuemax': 100,
              'aria-valuenow': Number((share * 100).toFixed(digits)),
              'aria-valuetext': text,
            }
          : // No value to report: an image named "<label>: loading / unknown", not a meter.
            { role: 'img', 'aria-label': `${label}: ${loading ? 'loading' : 'unknown'}` })}
        aria-busy={loading || undefined}
      >
        <span
          className={`${styles.fill} ${toneStyles.tone}`}
          data-tone={tone}
          style={{ '--share': `${share * 100}%` } as CSSProperties}
        />
      </div>
      {showValue && (
        <span className={styles.value} data-missing={!known || undefined} aria-hidden="true">
          {text}
        </span>
      )}
    </div>
  );
}
