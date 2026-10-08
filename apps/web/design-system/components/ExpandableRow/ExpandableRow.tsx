/**
 * ExpandableRow: one row of a list that opens its detail in place (a screener with its criteria,
 * hits and actions). The summary is a button with `aria-expanded` controlling the detail region;
 * it shows a title, an optional badge, a figure that stays on a phone (`essential`) and further
 * cells (`secondary`) that drop out in a narrow container. Controlled by the caller, so a list
 * keeps one row open at a time. For a labelled count with hidden detail use Disclosure.
 */
import { useId, type ReactNode } from 'react';

import { Icon } from '../Icon';
import styles from './ExpandableRow.module.css';

export interface ExpandableRowProps {
  /** The row's name. */
  title: ReactNode;
  /** A small pill beside the title (Mine / Preset). */
  badge?: ReactNode;
  /** The figure a phone keeps (hits today). */
  essential?: ReactNode;
  /** Cells shown beside the essential one only when the container is wide enough. */
  secondary?: ReactNode;
  /** Whether the detail is shown. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The detail; rendered only while open, so it can load lazily. */
  children: ReactNode;
}

export function ExpandableRow({
  title,
  badge,
  essential,
  secondary,
  open,
  onOpenChange,
  children,
}: ExpandableRowProps) {
  const id = useId();
  return (
    <div className={styles.root} data-open={open || undefined}>
      <button
        type="button"
        className={styles.summary}
        aria-expanded={open}
        aria-controls={`${id}-detail`}
        onClick={() => {
          onOpenChange(!open);
        }}
      >
        <span className={styles.chevron}>
          <Icon name="chevron-right" size="sm" tone="muted" />
        </span>
        <span className={styles.title}>{title}</span>
        {badge !== undefined && ' '}
        {badge !== undefined && <span className={styles.badge}>{badge}</span>}
        {secondary !== undefined && ' '}
        {secondary !== undefined && <span className={styles.secondary}>{secondary}</span>}
        {essential !== undefined && ' '}
        {essential !== undefined && <span className={styles.essential}>{essential}</span>}
      </button>
      <div id={`${id}-detail`} className={styles.detail} hidden={!open}>
        {open ? children : null}
      </div>
    </div>
  );
}
