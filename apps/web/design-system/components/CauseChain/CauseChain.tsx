/**
 * CauseChain: why something is not available, as an ordered chain read root to leaf: the source
 * that failed, the step that depended on it, the table left without rows, the features lost, the
 * run affected. Each link names its level, its subject (a code), an optional state as a
 * StatusBadge and an optional message; an arrow connects it to the next. Admin-only content: the
 * server sends a chain only to a role that may see it, and this component only draws it.
 */
import { Mono } from '../../primitives/Mono';
import { Text } from '../../primitives/Text';
import { StatusBadge, type StatusTone } from '../StatusBadge';
import styles from './CauseChain.module.css';

export type CauseLevel = 'SOURCE' | 'STEP' | 'TABLE' | 'FEATURE' | 'RUN';

export interface CauseLink {
  /** What kind of thing the link is; shown as a small label. */
  level: CauseLevel;
  /** The thing itself: a source, step, table, feature or run name. */
  subject: string;
  /** Its state in words (FAILED, SUCCEEDED, MISSING); shown as a badge, toned by its meaning. */
  status?: string;
  /** What went wrong, in a sentence or an error text. */
  message?: string;
}

export interface CauseChainProps {
  /** The links in reading order, root cause first. An empty list renders nothing. */
  links: readonly CauseLink[];
}

const LEVEL_LABEL: Record<CauseLevel, string> = {
  SOURCE: 'Source',
  STEP: 'Step',
  TABLE: 'Table',
  FEATURE: 'Features',
  RUN: 'Run',
};

const NEGATIVE = new Set(['FAILED', 'FAIL', 'ERROR', 'UNREACHABLE', 'MISSING', 'DOWN']);
const POSITIVE = new Set(['SUCCEEDED', 'COMPLETE', 'PASS', 'OK']);
const WARNING = new Set(['PARTIAL', 'WARN', 'STALE', 'WAIVED']);

/** The badge tone for a state word; an unrecognised state is neutral. */
export function statusTone(status: string): StatusTone {
  const word = status.toUpperCase();
  if (NEGATIVE.has(word)) return 'negative';
  if (POSITIVE.has(word)) return 'positive';
  if (WARNING.has(word)) return 'warning';
  return 'neutral';
}

export function CauseChain({ links }: CauseChainProps) {
  if (links.length === 0) return null;
  return (
    <ol className={styles.root} aria-label="Cause chain">
      {links.map((link, index) => (
        <li key={`${link.level}-${link.subject}-${index}`} className={styles.link}>
          <div className={styles.head}>
            <Text size="sm" tone="muted">
              {LEVEL_LABEL[link.level]}
            </Text>
            <span className={styles.subject}>
              <Mono>{link.subject}</Mono>
            </span>
            {link.status !== undefined && (
              <StatusBadge tone={statusTone(link.status)}>{link.status}</StatusBadge>
            )}
          </div>
          {link.message !== undefined && (
            <Text size="sm" tone="secondary">
              {link.message}
            </Text>
          )}
          {index < links.length - 1 && <span className={styles.arrow} aria-hidden="true" />}
        </li>
      ))}
    </ol>
  );
}
