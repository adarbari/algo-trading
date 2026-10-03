/**
 * One run record in a side sheet: its facts (job, session, status, timing, items), vendor pacing
 * when the run recorded it, and every item with its status. Opened from a drill-down; the
 * caller owns `open` and the run id.
 */
import {
  DataTable,
  Drawer,
  ErrorState,
  formatValue,
  Heading,
  KeyValue,
  Skeleton,
  Stack,
  type DataTableColumn,
  type KeyValueItem,
} from '@algotrade/ui';

import { useRun, useRunItems } from '../api/queries';
import { formatDuration } from '../model/duration';
import type { RunDetail, RunItem } from '../model/types';
import { RunStatusBadge } from './RunStatusBadge';

export interface RunRecordDrawerProps {
  runId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const ITEM_COLUMNS: DataTableColumn<RunItem>[] = [
  { id: 'key', header: 'Item', value: (i) => i.key, mono: true, width: 'md' },
  {
    id: 'code',
    header: 'Status',
    value: (i) => i.code,
    cell: ({ row }) => <RunStatusBadge status={row.code} />,
    width: 'md',
  },
  { id: 'status', header: 'Detail', value: (i) => i.status, tone: 'secondary', grow: true },
];

function facts(run: RunDetail): KeyValueItem[] {
  return [
    { label: 'Run', value: run.run_id, mono: true },
    { label: 'Job', value: run.job, mono: true },
    { label: 'Session', value: run.session, format: { kind: 'date', style: 'weekday' } },
    { label: 'Status', value: <RunStatusBadge status={run.status} /> },
    { label: 'Started', value: `${run.started_at.replace('T', ' ').slice(0, 19)} UTC`, mono: true },
    { label: 'Duration', value: formatDuration(run.duration_s) },
    { label: 'Items', value: run.items_total, format: { kind: 'number' } },
    ...Object.entries(run.items_by_status).map(([code, count]) => ({
      id: `status-${code}`,
      label: `${code} items`,
      value: count,
      format: { kind: 'number' } as const,
    })),
  ];
}

function pacing(run: RunDetail): KeyValueItem[] {
  const stored = run.stats['pacing'];
  if (!stored || typeof stored !== 'object') return [];
  return Object.entries(stored as Record<string, Record<string, unknown>>).map(([key, s]) => ({
    id: `pacing-${key}`,
    label: key,
    value: `${formatValue(s['requests'], { kind: 'number' }).text} requests · ${formatValue(s['throttled_429'], { kind: 'number' }).text} × 429 · waited ${formatDuration(Number(s['limiter_wait_s'] ?? 0))}`,
  }));
}

export function RunRecordDrawer({ runId, open, onOpenChange }: RunRecordDrawerProps) {
  const run = useRun(open ? runId : null);
  const items = useRunItems(runId, open);
  const vendor = run.data ? pacing(run.data) : [];
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Run record"
      description={runId ?? undefined}
    >
      <Stack gap={4}>
        {run.isError ? (
          <ErrorState
            compact
            title="The run record could not load."
            detail={run.error.message}
            onRetry={() => void run.refetch()}
            retrying={run.isFetching}
          />
        ) : (
          <KeyValue
            label="Run facts"
            items={run.data ? facts(run.data) : []}
            loading={run.isPending}
          />
        )}
        {vendor.length > 0 && (
          <Stack gap={2}>
            <Heading level={3}>Vendor pacing</Heading>
            <KeyValue label="Vendor pacing" items={vendor} />
          </Stack>
        )}
        <Stack gap={2}>
          <Heading level={3}>Items</Heading>
          {items.isPending ? (
            <Skeleton variant="table" rows={6} columns={3} label="Loading items…" />
          ) : (
            <DataTable
              label="Run items"
              columns={ITEM_COLUMNS}
              rows={items.data ?? []}
              getRowId={(i) => i.key}
              status={items.isError ? 'error' : 'ready'}
              errorMessage="The items could not load."
              emptyMessage="This run recorded no items."
              visibleRows={14}
            />
          )}
        </Stack>
      </Stack>
    </Drawer>
  );
}
