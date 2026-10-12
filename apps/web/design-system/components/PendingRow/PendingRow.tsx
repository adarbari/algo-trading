/**
 * PendingRow: a placeholder row for something that is not part of the screen yet, shown where it
 * will go (a criterion that waits on a formula the trader has not accepted). A dashed, muted
 * well, so it reads as "not active" by its border and its text label, never by colour alone:
 * the status label (with an optional help slot), the name in monospace, an optional summary
 * line and the actions that decide it (Review and add / Skip). It stacks at phone width. Every
 * word arrives as a prop; this component writes none.
 */
import type { ReactNode } from 'react';

import styles from './PendingRow.module.css';

export interface PendingRowProps {
  /** The short status label ("Waiting on formula"). */
  label: string;
  /** The help button for the label (the app's Guide drawer). */
  help?: ReactNode | undefined;
  /** What is waiting, in monospace (the field the criterion reads). */
  name: string;
  /** One line about it (the operator and threshold the criterion will have). */
  summary?: string | undefined;
  /** The decision: buttons, primary first. */
  actions?: ReactNode | undefined;
}

export function PendingRow({ label, help, name, summary, actions }: PendingRowProps) {
  return (
    <div className={styles.row} role="group" aria-label={`${label}: ${name}`}>
      <div className={styles.body}>
        <span className={styles.status}>
          <span className={styles.label}>{label}</span>
          {help}
        </span>
        <span className={styles.name}>{name}</span>
        {summary && <span className={styles.summary}>{summary}</span>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}
