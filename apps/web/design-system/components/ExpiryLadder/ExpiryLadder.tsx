/**
 * ExpiryLadder: the listed option expiries from near to far, one row each: the expiry date, its
 * days to expiry, and the events the expiry spans (an event on or before the expiry date, after
 * the close included) as EventChips with their days, or a "Clear" badge when it spans none. The
 * first clear row is marked ("First clear", an accent rule) so the first expiry that holds no
 * event is easy to find. The rows, the flags and the mark come from the caller (the API decides
 * what a row spans); the ladder draws them. A real table (caption = `label`), so it reads row by
 * row with a screen reader and wraps at phone width. Loading, empty and error states.
 */
import type { ReactNode } from 'react';

import { formatValue } from '../../format';
import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { EventChip, type EventItem } from '../EventChip';
import { Skeleton } from '../Skeleton';
import { StatusBadge } from '../StatusBadge';
import styles from './ExpiryLadder.module.css';

/** One expiry of the ladder. */
export interface ExpiryRow {
  /** The expiry date, ISO. */
  expiry: string;
  /** Calendar days from the session to the expiry. */
  dte: number;
  /** The events on or before the expiry date that it spans (empty when clear). */
  events: readonly EventItem[];
  /** True when the expiry spans no event. */
  clear: boolean;
  /** True on the nearest clear expiry (at most one row). */
  firstClear: boolean;
}

export interface ExpiryLadderProps {
  /** What the ladder is ("NVDA expiries, 7 to 90 days"): the table caption. */
  label: string;
  /** The expiries, nearest first. */
  rows: readonly ExpiryRow[];
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when there are no expiries. */
  emptyMessage?: ReactNode;
}

const weekday = (iso: string) => formatValue(iso, { kind: 'date', style: 'weekday' }).text;
const dayMonth = (iso: string) => formatValue(iso, { kind: 'date', style: 'day' }).text;

export function ExpiryLadder({
  label,
  rows,
  status = 'ready',
  errorMessage = 'The expiries could not load.',
  onRetry,
  emptyMessage = 'No listed expiries in this range.',
}: ExpiryLadderProps) {
  if (status === 'loading') {
    return <Skeleton variant="table" rows={6} columns={3} label={`Loading ${label}`} />;
  }
  if (status === 'error') {
    return (
      <ErrorState compact title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />
    );
  }
  if (rows.length === 0) return <EmptyState compact title={emptyMessage} />;

  return (
    <table className={styles.table}>
      <caption>
        <VisuallyHidden>{label}</VisuallyHidden>
      </caption>
      <thead>
        <tr>
          <th scope="col" className={styles.head}>
            Expiry
          </th>
          <th scope="col" className={styles.head} data-numeric="">
            DTE
          </th>
          <th scope="col" className={styles.head}>
            Events before expiry
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.expiry}
            className={styles.row}
            data-first-clear={row.firstClear || undefined}
          >
            <th scope="row" className={styles.expiry}>
              <Text mono>{weekday(row.expiry)}</Text>
            </th>
            <td className={styles.cell} data-numeric="">
              <Text numeric>{formatValue(row.dte, { kind: 'number' }).text}</Text>
            </td>
            <td className={styles.cell}>
              <div className={styles.events}>
                {row.clear ? (
                  <StatusBadge tone="positive">Clear</StatusBadge>
                ) : (
                  row.events.map((event) => (
                    <span
                      key={`${event.date}-${event.kind}-${event.label}`}
                      className={styles.event}
                    >
                      <EventChip kind={event.kind} label={event.label} event={event} />
                      <Text size="xs" tone="muted">
                        {dayMonth(event.date)}
                      </Text>
                    </span>
                  ))
                )}
                {row.firstClear && <StatusBadge tone="accent">First clear</StatusBadge>}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
