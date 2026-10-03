/**
 * StatusBadge: a short, tinted label for a state: a decision (QUALIFIED, WATCH, EVENT_RISK), a
 * check result (PASS, WARN, FAIL), a run state (COMPLETE, PARTIAL). The text always says the
 * state; colour only reinforces it. Tones map to the status tokens; `accent` is the one accent
 * hue (WATCH, selected). Not interactive: a filter is a Chip.
 */
import type { ReactNode } from 'react';

import { Icon, type IconName } from '../Icon';
import styles from './StatusBadge.module.css';

export type StatusTone = 'positive' | 'warning' | 'negative' | 'neutral' | 'info' | 'accent';

export interface StatusBadgeProps {
  /** positive (complete, pass), warning (partial, stale), negative (failed), neutral (draft, unknown), info (notes), accent (watch, selected). */
  tone?: StatusTone;
  /** An optional leading icon (check, alert, info). */
  icon?: IconName;
  /** Full explanation on hover ("Earnings in 6 sessions"). */
  title?: string;
  /** The state, in words. */
  children: ReactNode;
}

export function StatusBadge({ tone = 'neutral', icon, title, children }: StatusBadgeProps) {
  return (
    <span className={styles.badge} data-tone={tone} title={title}>
      {icon && <Icon name={icon} size="sm" />}
      {children}
    </span>
  );
}
