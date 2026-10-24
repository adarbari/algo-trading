/**
 * The data-status pill (owner 2026-10-23): one badge under the top bar of every page that says
 * which session's data the pages show and whether it is complete, partial, or a newer session is
 * processing or failed. Only the badge is in the entry chunk, its state from the status strip's
 * own request; the first click loads the popover (`DataStatusPopover`: the floating panel and
 * its detail read) and opens it. Every word of state and figure comes from the server
 * (`Session.dataStatus`); this file only names the four states. No data (pending, a failed read,
 * no session) shows nothing.
 */
import { lazy, Suspense, useState } from 'react';

import { Button, formatValue, ShortLabel, Stack, StatusBadge } from '@algotrade/ui';

import { DATA_STATE_TONE, useDataStatus, type PillView } from '@/entities/system-status';

const DataStatusPopover = lazy(() => import('./DataStatusPopover'));

export interface DataStatusPillProps {
  /** The viewer is an admin: the detail also shows the causes the server sent. */
  admin: boolean;
}

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'day' }).text;

/** The pill's words for a state and its dates. */
export function pillText(data: PillView): string {
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
const SHORT: Record<PillView['state'], string> = {
  COMPLETE: 'Data: complete',
  PARTIAL: 'Data: partial',
  NEXT_PROCESSING: 'Processing',
  NEXT_FAILED_SHOWING_PREVIOUS: 'Failed',
};

/** The badge, as the popover's trigger or, before the first click, a plain button. */
export function PillButton({ data, ...props }: { data: PillView; onClick?: () => void }) {
  return (
    <Button variant="ghost" size="sm" aria-label={pillText(data)} {...props}>
      <StatusBadge tone={DATA_STATE_TONE[data.state]}>
        <ShortLabel short={SHORT[data.state]}>{pillText(data)}</ShortLabel>
      </StatusBadge>
    </Button>
  );
}

export function DataStatusPill({ admin }: DataStatusPillProps) {
  const data = useDataStatus(admin);
  const [armed, setArmed] = useState(false);
  if (data === null) return null;
  const plain = (
    <PillButton
      data={data}
      onClick={() => {
        setArmed(true);
      }}
    />
  );
  return (
    <Stack direction="row" justify="end">
      {armed ? (
        <Suspense fallback={plain}>
          <DataStatusPopover data={data} admin={admin} />
        </Suspense>
      ) : (
        plain
      )}
    </Stack>
  );
}
