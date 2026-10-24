/**
 * SessionStrip: a row of small squares, one per session, oldest first, each in the tone of what
 * happened in it (ran, ran with a gap, did not run; the one being shown is outlined). Each square
 * is a focusable button (the row is a named group of them) named by its label ("Oct 22: Not run"); hovering, focusing or tapping
 * one writes its label in one caption under the strip, so colour is never the only signal (a
 * session that did not run is an empty dashed square) and the row stays a few elements long. A tap
 * opens a square's caption (no hover on a phone); a tap elsewhere closes it. Nothing is counted or derived: the caller says what each
 * means.
 */
import { useState } from 'react';

import { Text } from '../../primitives/Text';
import styles from './SessionStrip.module.css';

/** The colour role of a square: `positive` (ran), `warning` (ran with a gap), `muted` (did not run). */
export type SessionTone = 'positive' | 'warning' | 'muted';

export interface SessionStripItem {
  /** What the session was, in words ("Oct 22: Complete, 12 picked"); also its tooltip. */
  label: string;
  /** The square's colour role. */
  tone: SessionTone;
  /** The session the page is showing: outlined. */
  current?: boolean;
}

export interface SessionStripProps {
  /** The sessions, oldest first. */
  items: readonly SessionStripItem[];
  /** Accessible name of the strip, e.g. "Last 10 sessions". */
  label: string;
}

export function SessionStrip({ items, label }: SessionStripProps) {
  const [open, setOpen] = useState<number | null>(null);
  const shown = open === null ? undefined : items[open];
  return (
    <div className={styles.root}>
      <div className={styles.list} role="group" aria-label={label}>
        {items.map((item, index) => (
          <button
            type="button"
            className={styles.cell}
            data-tone={item.tone}
            data-current={item.current ? 'true' : undefined}
            aria-label={item.label}
            onMouseEnter={() => {
              setOpen(index);
            }}
            onMouseLeave={() => {
              setOpen(null);
            }}
            onFocus={() => {
              setOpen(index);
            }}
            onBlur={() => {
              setOpen(null);
            }}
            onClick={() => {
              setOpen(index);
            }}
          />
        ))}
      </div>
      {shown ? (
        <Text size="sm" tone="secondary" aria-live="polite">
          {shown.label}
        </Text>
      ) : null}
    </div>
  );
}
