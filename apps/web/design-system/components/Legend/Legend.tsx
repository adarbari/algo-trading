/**
 * Legend: the key to a chart, bar or grid. A wrapped row of swatches, each with its label and an
 * optional value (`OK 3,624`). Swatches are status tones (`positive` ... `info`, `empty` for
 * "not collected"), the data series `s1`-`s6`, `accent` or `muted`; colour is never the only key,
 * so every swatch carries its label as text.
 */
import type { ReactNode } from 'react';

import type { Series, Status } from '../../tokens';
import styles from './Legend.module.css';
import tones from './tones.module.css';

/** A colour role a data mark can take: a status, a series, the accent, muted or empty (no data). */
export type DataTone = Status | Series | 'accent' | 'muted' | 'empty';

export interface LegendItem {
  /** Stable key (defaults to the label). */
  id?: string;
  label: ReactNode;
  tone: DataTone;
  /** Shown after the label (a count or share), tabular. */
  value?: ReactNode;
}

export interface LegendProps {
  items: readonly LegendItem[];
  /**
   * Swatch shape: `cell` (tinted fill + border, matches HeatGrid cells), `solid` (bars and
   * areas, the default), `line` (chart lines) or `hatch` (diagonal lines in the tone, for a
   * hatched chart band).
   */
  swatch?: 'cell' | 'solid' | 'line' | 'hatch';
  /** Accessible name of the list, e.g. "Status key". */
  label?: string;
  /** Text size: `sm` 12 px (default) or `xs` 11.5 px. */
  size?: 'sm' | 'xs';
}

export function Legend({ items, swatch = 'solid', label = 'Legend', size = 'sm' }: LegendProps) {
  return (
    <ul className={styles.legend} aria-label={label} data-size={size}>
      {items.map((item, index) => (
        <li
          key={item.id ?? (typeof item.label === 'string' ? item.label : index)}
          className={styles.item}
        >
          <span
            className={`${styles.swatch} ${tones.tone}`}
            data-swatch={swatch}
            data-tone={item.tone}
            aria-hidden="true"
          >
            {swatch === 'hatch' && (
              <svg viewBox="0 0 10 10" className={styles.hatch} focusable="false">
                <path d="M-1 5 L5 -1 M-1 11 L11 -1 M5 11 L11 5" />
              </svg>
            )}
          </span>
          <span className={styles.label}>{item.label}</span>
          {item.value !== undefined && <span className={styles.value}>{item.value}</span>}
        </li>
      ))}
    </ul>
  );
}
