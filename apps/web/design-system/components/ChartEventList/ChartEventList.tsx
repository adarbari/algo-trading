/**
 * ChartEventList: the events a price chart marks (its `ChartEvent`s), as a dated list under it:
 * one row per marker, in the order given, each a date, the kind's letter (the chart's own: E earnings, F filing, D
 * ex-dividend, S split, M macro release) and a description. A description is one or more
 * parts: a part with an address is an external link (the source page, opens in a new tab), one
 * without is plain text, so several 8-Ks of one day stay separate links inside one row. Under
 * the list's width of a phone the row folds to the date and the letter on one line and the
 * description below. Kind chips above toggle which kinds show, each with how many rows it has;
 * all show at first. Loading, empty and error states.
 */
import { useState, type ReactNode } from 'react';

import { formatValue } from '../../format';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import {
  CHART_EVENT_KINDS as EVENT_KINDS,
  type ChartEvent,
  type ChartEventKind,
  type ChartEventPart,
} from '../Chart';
import { Chip } from '../Chip';
import { EmptyState } from '../EmptyState';
import { ErrorState } from '../ErrorState';
import { ExternalLink } from '../ExternalLink';
import { Skeleton } from '../Skeleton';
import styles from './ChartEventList.module.css';

export interface ChartEventListProps {
  /** What the list is ("AAPL events on the chart"): its accessible name. */
  label: string;
  /** The markers, already in display order (newest first). */
  events: readonly ChartEvent[];
  /** `ready` (default), `loading` or `error`. */
  status?: 'ready' | 'loading' | 'error';
  errorMessage?: ReactNode;
  onRetry?: () => void;
  /** Shown when there is no row at all. */
  emptyMessage?: ReactNode;
}

const KINDS = Object.keys(EVENT_KINDS) as ChartEventKind[];

/** The words of a row: its parts, else the detail after the kind's name, else the name. */
function partsOf(event: ChartEvent): readonly ChartEventPart[] {
  if (event.parts !== undefined && event.parts.length > 0) return event.parts;
  const name = EVENT_KINDS[event.kind].label;
  return [{ text: event.detail ? `${name} ${event.detail}` : name }];
}

function Description({ parts }: { parts: readonly ChartEventPart[] }) {
  return (
    <Stack direction="row" gap={2} wrap>
      {parts.map((part, i) =>
        part.href === undefined ? (
          <Text key={`${String(i)}-${part.text}`} size="sm">
            {part.text}
          </Text>
        ) : (
          <ExternalLink key={`${String(i)}-${part.text}`} href={part.href} size="sm">
            {part.text}
          </ExternalLink>
        ),
      )}
    </Stack>
  );
}

export function ChartEventList({
  label,
  events,
  status = 'ready',
  errorMessage = 'The events could not load.',
  onRetry,
  emptyMessage = 'No events on the chart in this range.',
}: ChartEventListProps) {
  const [hidden, setHidden] = useState<ReadonlySet<ChartEventKind>>(new Set());
  if (status === 'loading') {
    return <Skeleton variant="rect" height="sm" label={`Loading ${label}`} />;
  }
  if (status === 'error') {
    return (
      <ErrorState compact title={errorMessage} {...(onRetry === undefined ? {} : { onRetry })} />
    );
  }
  if (events.length === 0) return <EmptyState compact title={emptyMessage} />;
  const shown = events.filter((e) => !hidden.has(e.kind));
  return (
    <div className={styles.root}>
      <Stack direction="row" gap={1} align="center" wrap>
        {KINDS.map((kind) => {
          const count = events.filter((e) => e.kind === kind).length;
          if (count === 0) return null;
          return (
            <Chip
              key={kind}
              label={`${EVENT_KINDS[kind].label} ${String(count)}`}
              selected={!hidden.has(kind)}
              onSelectedChange={(on) => {
                const next = new Set(hidden);
                if (on) next.delete(kind);
                else next.add(kind);
                setHidden(next);
              }}
            />
          );
        })}
      </Stack>
      {shown.length === 0 ? (
        <EmptyState compact title="No kind is selected." description="Select a kind above." />
      ) : (
        <ol className={styles.list} aria-label={label}>
          {shown.map((event, i) => (
            <li key={`${event.time}-${event.kind}-${String(i)}`} className={styles.row}>
              <span className={styles.date}>
                <Text size="sm" tone="secondary">
                  {formatValue(event.time, { kind: 'date' }).text}
                </Text>
              </span>
              <span
                className={styles.kind}
                data-kind={event.kind}
                title={EVENT_KINDS[event.kind].label}
              >
                <span aria-hidden="true">{EVENT_KINDS[event.kind].letter}</span>
                <VisuallyHidden>{EVENT_KINDS[event.kind].label}</VisuallyHidden>
              </span>
              <span className={styles.description}>
                <Description parts={partsOf(event)} />
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
