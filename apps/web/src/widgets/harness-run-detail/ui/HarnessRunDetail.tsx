/**
 * One run's stored rows (the figures it wrote, per variant, horizon and slice), beside the
 * runs list (a sheet on a phone). The words are the server's; each term carries its Guide button.
 */
import { DataTable, EmptyState, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import { rowKey, useHarnessRunRows, type HarnessRow } from '@/entities/harness-run';

import { rowColumns } from '../model/columns';

export interface HarnessRunDetailProps {
  /** The chosen run's id (from the URL), or null. */
  id: string | null;
}

export function HarnessRunDetail({ id }: HarnessRunDetailProps) {
  const found = useHarnessRunRows(id);
  const columns = useMemo(() => rowColumns(), []);
  if (!id) return <EmptyState title="Choose a run" icon="search" bordered />;
  const run = found.data;
  const rows = run?.rows ?? [];
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
      <DataTable<HarnessRow>
        label="Run rows"
        columns={columns}
        rows={rows}
        getRowId={rowKey}
        sortMode="client"
        emptyMessage="The run holds no rows."
      />
    </Panel>
  );
}
