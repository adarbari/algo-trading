/**
 * The data-status pill (owner 2026-10-23): one badge in the top bar of every page that says
 * which session's data the pages show and whether it is complete, partial, or a newer session is
 * processing or failed. A click opens the detail (lazy: the entry chunk carries only the badge).
 * Every word of state and figure comes from the server (`Session.dataStatus`); this file only
 * names the four states. No data (pending, a failed read, no session) shows nothing.
 */
import { lazy, Suspense } from 'react';

import { Button, formatValue, Popover, ShortLabel, Skeleton, StatusBadge } from '@algotrade/ui';

import { DATA_STATE_TONE, useDataStatus, type DataStatusView } from '@/entities/system-status';

const DataStatusPanel = lazy(() => import('./DataStatusPanel'));

export interface DataStatusPillProps {
  /** The viewer is an admin: the detail also shows the causes the server sent. */
  admin: boolean;
}

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'day' }).text;

/** The pill's words for a state and its dates. */
export function pillText(data: DataStatusView): string {
  const shown = day(data.date);
  const next = data.newerDate === null ? shown : day(data.newerDate);
  switch (data.state) {
    case 'COMPLETE':
      return `Data: ${shown}, complete`;
    case 'PARTIAL':
      return `Data: ${shown}, partial`;
    case 'NEXT_PROCESSING':
      return `${next} is processing`;
    case 'NEXT_FAILED_SHOWING_PREVIOUS':
      return `${next} failed, showing ${shown}`;
  }
}

/** The phone's wording: the date is in the popover. */
const SHORT: Record<DataStatusView['state'], string> = {
  COMPLETE: 'Data: complete',
  PARTIAL: 'Data: partial',
  NEXT_PROCESSING: 'Processing',
  NEXT_FAILED_SHOWING_PREVIOUS: 'Failed',
};

export function DataStatusPill({ admin }: DataStatusPillProps) {
  const data = useDataStatus(admin);
  if (data === null) return null;
  return (
    <Popover
      label="Data status"
      placement="bottom-end"
      width="wide"
      trigger={(props) => (
        <Button variant="ghost" size="sm" aria-label={pillText(data)} {...props}>
          <StatusBadge tone={DATA_STATE_TONE[data.state]}>
            <ShortLabel short={SHORT[data.state]}>{pillText(data)}</ShortLabel>
          </StatusBadge>
        </Button>
      )}
    >
      <Suspense fallback={<Skeleton lines={3} label="Loading the data status" />}>
        <DataStatusPanel data={data} admin={admin} />
      </Suspense>
    </Popover>
  );
}
