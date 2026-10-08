/**
 * StatusStrip: one slim line under the top bar of every page that says what is wrong with the
 * system, instead of a stack of banners. Severity pills ("1 failing", "2 warnings"), the most
 * serious message and "and N more"; the whole line is one button that expands the full list,
 * each issue with its title, detail, its own actions and a snooze. Issues arrive most serious
 * first. With no issue it renders nothing, or the slim `allClear` line when the caller gives
 * one. Presentational: the caller decides what an issue is and where a snooze is remembered
 * (`onSnooze`); the words are props with English defaults. Container query: under 480 px an
 * issue's actions drop under its text.
 */
import { useId, useState, type ReactNode } from 'react';

import { Button } from '../Button';
import { Icon } from '../Icon';
import { StatusBadge } from '../StatusBadge';
import styles from './StatusStrip.module.css';

export type StatusIssueSeverity = 'failing' | 'warning';

export interface StatusIssue {
  /** A stable id: a snoozed issue returns when its id changes. */
  id: string;
  /** `failing` (something broke) or `warning` (degraded, or not yet done). */
  severity: StatusIssueSeverity;
  /** The one-line message. */
  title: ReactNode;
  /** What it means and what it blocks. */
  detail?: ReactNode;
  /** Buttons or links that fix or explain it ("View run", "Retry"). */
  actions?: ReactNode;
}

export interface StatusStripWords {
  failing: (count: number) => string;
  warnings: (count: number) => string;
  more: (count: number) => string;
  snooze: string;
}

export interface StatusStripProps {
  /** The open issues, most serious first. */
  issues: readonly StatusIssue[];
  /** Hides one issue (a per-viewer snooze); without it the list has no snooze button. */
  onSnooze?: (id: string) => void;
  /** The slim all-clear line ("All systems normal"); omitted, a clear system shows nothing. */
  allClear?: ReactNode;
  /** Start expanded (default false). */
  defaultExpanded?: boolean;
  /** Accessible name of the strip. */
  label?: string;
  /** Words: the pills, "and N more" and the snooze button. */
  words?: Partial<StatusStripWords>;
}

const WORDS: StatusStripWords = {
  failing: (n) => `${n} failing`,
  warnings: (n) => (n === 1 ? '1 warning' : `${n} warnings`),
  more: (n) => `and ${n} more`,
  snooze: 'Snooze 24h',
};

export function StatusStrip({
  issues,
  onSnooze,
  allClear,
  defaultExpanded = false,
  label = 'System status',
  words,
}: StatusStripProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const listId = useId();
  const w = { ...WORDS, ...words };
  const first = issues[0];
  if (!first) {
    if (allClear === undefined) return null;
    return (
      <section className={styles.strip} aria-label={label}>
        <div className={styles.bar}>
          <StatusBadge tone="positive" icon="check">
            {allClear}
          </StatusBadge>
        </div>
      </section>
    );
  }
  const failing = issues.filter((i) => i.severity === 'failing').length;
  const warnings = issues.length - failing;
  return (
    <section className={styles.strip} aria-label={label}>
      <button
        type="button"
        className={styles.bar}
        data-action=""
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => {
          setExpanded((open) => !open);
        }}
      >
        {failing > 0 && <StatusBadge tone="negative">{w.failing(failing)}</StatusBadge>}
        {warnings > 0 && <StatusBadge tone="warning">{w.warnings(warnings)}</StatusBadge>}
        <span className={styles.summary}>{first.title}</span>
        {issues.length > 1 && <span className={styles.more}>{w.more(issues.length - 1)}</span>}
        <span className={styles.chevron}>
          <Icon name="chevron-down" size="sm" tone="muted" />
        </span>
      </button>
      {expanded && (
        <ul id={listId} className={styles.list}>
          {issues.map((issue) => (
            <li key={issue.id} className={styles.issue} data-severity={issue.severity}>
              <div className={styles.text}>
                <span className={styles.title}>{issue.title}</span>
                {issue.detail !== undefined && (
                  <span className={styles.detail}>{issue.detail}</span>
                )}
              </div>
              <div className={styles.actions}>
                {issue.actions}
                {onSnooze && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      onSnooze(issue.id);
                    }}
                  >
                    {w.snooze}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
