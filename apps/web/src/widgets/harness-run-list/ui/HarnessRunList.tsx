/**
 * The edge evaluation runs, newest first, of any status; choosing a row (a click or Enter)
 * selects it and the page shows its rows beside the list.
 */
import { DataTable, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import { useHarnessRuns, type HarnessRun } from '@/entities/harness-run';

import { runColumns } from '../model/columns';

export interface HarnessRunListProps {
  /** The chosen run's id (from the URL), or null. */
  selected: string | null;
  onSelect: (id: string) => void;
}

export function HarnessRunList({ selected, onSelect }: HarnessRunListProps) {
  const runs = useHarnessRuns();
  const columns = useMemo(() => runColumns(), []);
  const rows = runs.data ?? [];
  const state =
    runs.isError && !runs.data
      ? 'error'
      : runs.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title="Harness runs"
      flush
      state={state}
      loadingLabel="Loading harness runs…"
      emptyMessage="No evaluation run is recorded."
      errorMessage="The harness runs failed to load."
      onRetry={() => void runs.refetch()}
    >
      <DataTable<HarnessRun>
        label="Harness runs"
        columns={columns}
        rows={rows}
        getRowId={(r) => r.runId}
        getRowLabel={(r) => `${r.edgeId} ${r.runId}`}
        activeRowId={selected}
        onRowActivate={(r) => {
          onSelect(r.runId);
        }}
        sortMode="client"
        emptyMessage="No evaluation run is recorded."
      />
    </Panel>
  );
}
