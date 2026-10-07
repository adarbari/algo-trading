/**
 * EventTimeline: dated events over a window (the next 90 days; the trailing 24 months of
 * filings). A horizontal axis with a mark per event day and a tick per month start shows where
 * they fall; under it the days with events are listed oldest first, each with its date and one
 * EventChip per event (hover or focus: label, time, source, known-from). `dense` collapses each
 * day to a count whose tooltip lists the day's events, for a long window or a narrow panel. Days
 * wrap, so it works at phone width. The list is the accessible content (an ordered list named by
 * `label`); the axis is decoration. Loading, empty and error states.
 */
import type { CSSProperties, ReactNode } from 'react';

import { formatValue } from '../../format';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { EventChip, EventDetail, type EventItem } from '../EventChip';
import { Skeleton } from '../Skeleton';
import { Tooltip } from '../Tooltip';
import { fraction, groupByDay, monthStarts } from './axis';
import styles from './EventTimeline.module.css';

export interface EventTimelineProps {
  /** What the timeline shows ("NVDA events, next 90 days"): the list's accessible name. */
  label: string;
  /** The events (any order); those outside the window are not drawn. */
  events: readonly EventItem[];
  /** First day of the window, ISO. */
  start: string;
  /** Last day of the window, ISO (inclusive). */
  end: string;
  /** Collapse each day to a count (its tooltip lists the events). Default false. */
  dense?: boolean;
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when no event falls in the window. */
  emptyMessage?: ReactNode;
}

const dayText = (iso: string) => formatValue(iso, { kind: 'date', style: 'weekday' }).text;
const monthText = (iso: string) => formatValue(iso, { kind: 'date', style: 'day' }).text;
const at = (value: number) =>
  ({ '--at': `${String(Number((value * 100).toFixed(3)))}%` }) as CSSProperties;

export function EventTimeline({
  label,
  events,
  start,
  end,
  dense = false,
  status = 'ready',
  errorMessage = 'The events could not load.',
  onRetry,
  emptyMessage = 'No events in this window.',
}: EventTimelineProps) {
  if (status === 'loading')
    return <Skeleton variant="rect" height="sm" label={`Loading ${label}`} />;
  if (status === 'error') {
    return (
      <ErrorState compact title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />
    );
  }
  const days = groupByDay(events, start, end);
  if (days.length === 0) return <EmptyState compact title={emptyMessage} />;

  return (
    <div className={styles.root}>
      <div className={styles.axis} aria-hidden="true">
        <span className={styles.track} />
        {monthStarts(start, end).map((month) => (
          <span key={month} className={styles.tick} style={at(fraction(month, start, end))}>
            <span className={styles.tickLabel}>{monthText(month)}</span>
          </span>
        ))}
        {days.map((day) => (
          <span
            key={day.date}
            className={styles.mark}
            data-kind={
              day.events.every((e) => e.kind === day.events[0]?.kind)
                ? day.events[0]?.kind
                : undefined
            }
            data-multiple={day.events.length > 1 || undefined}
            style={at(fraction(day.date, start, end))}
          />
        ))}
      </div>
      <ol className={styles.days} aria-label={label} data-dense={dense || undefined}>
        {days.map((day) => (
          <li key={day.date} className={styles.day}>
            <Text size="xs" tone="muted" mono>
              {dayText(day.date)}
            </Text>
            {dense ? (
              <Tooltip
                delay="none"
                content={
                  <Stack gap={1.5}>
                    {day.events.map((event) => (
                      <EventDetail key={`${event.kind}-${event.label}`} event={event} />
                    ))}
                  </Stack>
                }
              >
                {(trigger) => (
                  <button
                    type="button"
                    className={styles.count}
                    aria-label={`${dayText(day.date)}: ${String(day.events.length)} ${day.events.length === 1 ? 'event' : 'events'}`}
                    {...trigger}
                  >
                    {day.events.length}
                    <span className={styles.countLabel}>
                      {day.events.length === 1 ? ' event' : ' events'}
                    </span>
                  </button>
                )}
              </Tooltip>
            ) : (
              <Stack gap={1}>
                {day.events.map((event) => (
                  <EventChip
                    key={`${event.kind}-${event.label}`}
                    kind={event.kind}
                    label={event.label}
                    event={event}
                  />
                ))}
              </Stack>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
