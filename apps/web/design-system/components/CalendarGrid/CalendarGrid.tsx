/**
 * CalendarGrid: the cross-name event calendar. Days on one axis, names (tickers) on the other,
 * an EventChip in each cell that has events (hover or focus: label, time, source, known-from).
 * Days run down the rows with the names as columns; when the grid's own width is under the
 * medium breakpoint (a phone) the axes flip, days across and names down, so the grid scrolls the
 * long axis instead of squeezing the names (`orientation` forces either). Days in `ruledDays`
 * (the expiry Fridays) carry a rule across the grid and the rule's name in the day header.
 * Beyond `pageSize` names (default 30) the names are paged, with Previous / Next and a "Names
 * 1-30 of 64" line. A real table (caption = `label`, row and column headers). Loading, empty and
 * error states.
 */
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';

import { formatValue } from '../../format';
import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { breakpoint } from '../../tokens';
import { Button } from '../Button';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { EventChip } from '../EventChip';
import { Skeleton } from '../Skeleton';
import {
  cellKey,
  cellsOf,
  namesOf,
  pageOf,
  type CalendarDay,
  type CalendarEvent,
  type CalendarName,
} from './calendarModel';
import styles from './CalendarGrid.module.css';

export interface CalendarGridProps {
  /** What the grid shows ("Events, next 90 days: scope list"): the table caption. */
  label: string;
  /** The days, oldest first, each with its events. */
  days: readonly CalendarDay[];
  /** The names (columns, or rows when flipped), in order; default the distinct names in the events. */
  names?: readonly CalendarName[];
  /** Days that carry a rule across the grid (the expiry Fridays), ISO. */
  ruledDays?: readonly string[];
  /** What a ruled day is called in its header ("Expiry"). */
  ruleLabel?: string;
  /** `auto` (default): days down, flipping to days across under the medium breakpoint; or force one. */
  orientation?: 'auto' | 'days-down' | 'days-across';
  /** Names per page (default 30). */
  pageSize?: number;
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when no day has an event. */
  emptyMessage?: ReactNode;
}

const dayHead = (iso: string) => formatValue(iso, { kind: 'date', style: 'weekday' }).text;

/** True while the element is narrower than the medium breakpoint (false until measured). */
function useNarrow(): [RefObject<HTMLDivElement | null>, boolean] {
  const ref = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      setNarrow(width > 0 && width < breakpoint.md);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);
  return [ref, narrow];
}

function Cell({ events, ruled }: { events: readonly CalendarEvent[] | undefined; ruled: boolean }) {
  return (
    <td className={styles.cell} data-ruled={ruled || undefined}>
      <div className={styles.chips}>
        {events?.map((event) => (
          <EventChip
            key={`${event.kind}-${event.label}`}
            kind={event.kind}
            label={event.label}
            event={event}
          />
        ))}
      </div>
    </td>
  );
}

export function CalendarGrid({
  label,
  days,
  names,
  ruledDays = [],
  ruleLabel = 'Expiry',
  orientation = 'auto',
  pageSize = 30,
  status = 'ready',
  errorMessage = 'The calendar could not load.',
  onRetry,
  emptyMessage = 'No events in this window.',
}: CalendarGridProps) {
  const [ref, narrow] = useNarrow();
  const [page, setPage] = useState(0);
  const acrossDays = orientation === 'auto' ? narrow : orientation === 'days-across';

  if (status === 'loading') {
    return <Skeleton variant="table" rows={8} columns={5} label={`Loading ${label}`} />;
  }
  if (status === 'error') {
    return (
      <ErrorState compact title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />
    );
  }
  if (!days.some((day) => day.events.length > 0)) {
    return <EmptyState compact title={emptyMessage} />;
  }

  const all = namesOf(days, names);
  const shown = pageOf(all, page, Math.max(1, pageSize));
  const cells = cellsOf(days);
  const ruled = new Set(ruledDays);
  const dayHeader = (day: CalendarDay) => (
    <>
      <Text mono>{dayHead(day.date)}</Text>
      {ruled.has(day.date) && (
        <Text size="xs" tone="muted">
          {ruleLabel}
        </Text>
      )}
    </>
  );

  return (
    <div ref={ref} className={styles.root}>
      {all.length > pageSize && (
        <div className={styles.pager}>
          <Text size="sm" tone="muted" numeric>
            {`Names ${String(shown.from)}-${String(shown.to)} of ${String(all.length)}`}
          </Text>
          <Button
            size="sm"
            variant="secondary"
            disabled={shown.page === 0}
            onClick={() => {
              setPage(shown.page - 1);
            }}
          >
            Previous names
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={shown.page >= shown.pages - 1}
            onClick={() => {
              setPage(shown.page + 1);
            }}
          >
            Next names
          </Button>
        </div>
      )}
      <div className={styles.scroller}>
        <table className={styles.table} data-orientation={acrossDays ? 'days-across' : 'days-down'}>
          <caption>
            <VisuallyHidden>{label}</VisuallyHidden>
          </caption>
          <thead>
            <tr>
              <td className={styles.corner}>
                <VisuallyHidden>{acrossDays ? 'Name' : 'Day'}</VisuallyHidden>
              </td>
              {acrossDays
                ? days.map((day) => (
                    <th
                      key={day.date}
                      scope="col"
                      className={styles.head}
                      data-ruled={ruled.has(day.date) || undefined}
                    >
                      {dayHeader(day)}
                    </th>
                  ))
                : shown.items.map((name) => (
                    <th key={name.id} scope="col" className={styles.head}>
                      <Text mono>{name.symbol}</Text>
                    </th>
                  ))}
            </tr>
          </thead>
          <tbody>
            {acrossDays
              ? shown.items.map((name) => (
                  <tr key={name.id}>
                    <th scope="row" className={styles.side}>
                      <Text mono>{name.symbol}</Text>
                    </th>
                    {days.map((day) => (
                      <Cell
                        key={day.date}
                        events={cells.get(cellKey(day.date, name.id))}
                        ruled={ruled.has(day.date)}
                      />
                    ))}
                  </tr>
                ))
              : days.map((day) => (
                  <tr key={day.date}>
                    <th
                      scope="row"
                      className={styles.side}
                      data-ruled={ruled.has(day.date) || undefined}
                    >
                      {dayHeader(day)}
                    </th>
                    {shown.items.map((name) => (
                      <Cell
                        key={name.id}
                        events={cells.get(cellKey(day.date, name.id))}
                        ruled={ruled.has(day.date)}
                      />
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
