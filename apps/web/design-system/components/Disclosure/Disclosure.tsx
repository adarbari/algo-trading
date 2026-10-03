/**
 * Disclosure: a summary row (label + count) that expands to show detail: grouped issues
 * ("Stale: 515"), a rule's explanation, an advanced section. The summary is a button with
 * `aria-expanded` controlling the detail region. Controlled (`open` + `onOpenChange`) or
 * uncontrolled (`defaultOpen`). `boxed` (default) draws the soft border of grouped issues.
 */
import { useId, useState, type ReactNode } from 'react';

import styles from './Disclosure.module.css';

export interface DisclosureProps {
  /** The summary text. */
  label: ReactNode;
  /** A count (or short value) at the end of the summary row. */
  count?: ReactNode;
  /** Colour of the count: default text, or a status. */
  countTone?: 'default' | 'positive' | 'warning' | 'negative' | 'muted';
  /** Controlled open state (pair with `onOpenChange`). */
  open?: boolean;
  /** Initial open state when uncontrolled. */
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** `boxed` (soft border, default) or `plain` (a row in a list that draws its own dividers). */
  variant?: 'boxed' | 'plain';
  /** The detail shown when open. */
  children: ReactNode;
}

export function Disclosure({
  label,
  count,
  countTone = 'default',
  open,
  defaultOpen = false,
  onOpenChange,
  variant = 'boxed',
  children,
}: DisclosureProps) {
  const id = useId();
  const [ownOpen, setOwnOpen] = useState(defaultOpen);
  const isOpen = open ?? ownOpen;
  const toggle = () => {
    if (open === undefined) setOwnOpen(!isOpen);
    onOpenChange?.(!isOpen);
  };
  return (
    <div className={styles.root} data-variant={variant} data-open={isOpen || undefined}>
      <button
        type="button"
        className={styles.summary}
        aria-expanded={isOpen}
        aria-controls={`${id}-detail`}
        onClick={toggle}
      >
        <svg className={styles.chevron} viewBox="0 0 12 12" aria-hidden="true" focusable="false">
          <path d="M4 2.5 7.5 6 4 9.5" />
        </svg>
        <span className={styles.label}>{label}</span>
        {count !== undefined && ' '}
        {count !== undefined && (
          <span className={styles.count} data-tone={countTone}>
            {count}
          </span>
        )}
      </button>
      <div id={`${id}-detail`} className={styles.detail} hidden={!isOpen}>
        {children}
      </div>
    </div>
  );
}
