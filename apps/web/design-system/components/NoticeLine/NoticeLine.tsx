/**
 * NoticeLine: a condition worth knowing about in one line (a tinted pill with a count or a few
 * words, then the first reason, truncated) that expands on a click or tap to its full content.
 * Keeps a page's data starting near the top where a Banner would push it down. The button
 * carries `aria-expanded` and `aria-controls`; colour only reinforces the pill's words.
 */
import { useId, useState, type ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { Icon } from '../Icon';
import { StatusBadge, type StatusTone } from '../StatusBadge';
import styles from './NoticeLine.module.css';

export interface NoticeLineProps {
  /** The pill's tone (default `warning`). */
  tone?: Exclude<StatusTone, 'accent'>;
  /** The pill's words ("6 unavailable"). */
  label: ReactNode;
  /** The first reason, one line, truncated. */
  summary?: ReactNode;
  /** Open on first render (default closed). */
  defaultOpen?: boolean;
  /** The full content shown when expanded. */
  children?: ReactNode;
}

export function NoticeLine({
  tone = 'warning',
  label,
  summary,
  defaultOpen = false,
  children,
}: NoticeLineProps) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={styles.root}>
      <button
        type="button"
        className={styles.line}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          setOpen((now) => !now);
        }}
      >
        <StatusBadge tone={tone} icon="alert">
          {label}
        </StatusBadge>
        {summary !== undefined && (
          <span className={styles.summary}>
            <Text size="sm" tone="muted">
              {summary}
            </Text>
          </span>
        )}
        <span className={styles.chevron}>
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size="sm" />
        </span>
      </button>
      {open && (
        <div id={id} className={styles.content}>
          {children}
        </div>
      )}
    </div>
  );
}
