/**
 * One run's stored rows (the figures it wrote, per variant, horizon and slice), beside the
 * runs list (a sheet on a phone). The words are the server's; each term carries its Guide button.
 */
import { DataTable, EmptyState, Panel, Stack } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  rowKey,
  useHarnessRunRows,
  type HarnessLostInput,
  type HarnessRow,
} from '@/entities/harness-run';

import { lostColumns, rowColumns } from '../model/columns';

export interface HarnessRunDetailProps {
  /** The chosen run's id (from the URL), or null. */
  id: string | null;
}

export function HarnessRunDetail({ id }: HarnessRunDetailProps) {
  const found = useHarnessRunRows(id);
  const columns = useMemo(() => rowColumns(), []);
  const lostCols = useMemo(() => lostColumns(), []);
  if (!id) return <EmptyState title="Choose a run" icon="search" bordered />;
  const run = found.data;
  const rows = run?.rows ?? [];
  const lost = run?.lostInputs ?? [];
  const state =
    found.isError && !run
      ? 'error'
      : found.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title={id}
      flush
      state={state}
      loadingLabel="Loading run rows…"
      emptyMessage="The run holds no rows."
      errorMessage="The run's rows failed to load."
      onRetry={() => void found.refetch()}
    >
      <Stack gap={4}>
        <DataTable<HarnessRow>
          label="Run rows"
          columns={columns}
          rows={rows}
          getRowId={rowKey}
          sortMode="client"
          emptyMessage="The run holds no rows."
        />
        {lost.length > 0 && (
          <DataTable<HarnessLostInput>
            label="Missing input tables"
            columns={lostCols}
            rows={lost}
            getRowId={(l) => `${l.variant}/${l.horizon}/${l.table}`}
            sortMode="client"
            emptyMessage="No input table was missing."
          />
        )}
      </Stack>
    </Panel>
  );
}
