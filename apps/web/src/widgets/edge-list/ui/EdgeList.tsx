/**
 * The edges: one row each under its verdict (Works, Promising, Not working, Not enough data,
 * Waiting on data), with its screens, the out-of-sample result, the trades and the status.
 * Choosing a row (a click or Enter) opens the edge's page.
 */
import { DataTable, Panel, type DataTableGroupBy } from '@algotrade/ui';
import { useMemo } from 'react';

import { useEdges, verdictLabel, VERDICT_ORDER, type Edge } from '@/entities/edge';

import { edgeColumns } from '../model/columns';

export interface EdgeListProps {
  /** Open the chosen edge's page. */
  onSelect: (id: string) => void;
}

const GROUPS: DataTableGroupBy<Edge> = {
  getGroup: (e) => e.verdict.verdict,
  order: VERDICT_ORDER,
  label: (group, count) => `${verdictLabel(group)} · ${String(count)}`,
};

export function EdgeList({ onSelect }: EdgeListProps) {
  const edges = useEdges();
  const columns = useMemo(() => edgeColumns(), []);
  const rows = edges.data ?? [];
  const state =
    edges.isError && !edges.data
      ? 'error'
      : edges.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title="Edges"
      flush
      state={state}
      loadingLabel="Loading edges…"
      emptyMessage="No edge is declared."
      errorMessage="The edges failed to load."
      onRetry={() => void edges.refetch()}
    >
      <DataTable<Edge>
        label="Edges"
        columns={columns}
        rows={rows}
        getRowId={(e) => e.id}
        getRowLabel={(e) => e.name}
        onRowActivate={(e) => {
          onSelect(e.id);
        }}
        groupBy={GROUPS}
        rowLines={2}
        defaultSort={{ columnId: 'name', direction: 'asc' }}
        emptyMessage="No edge is declared."
      />
    </Panel>
  );
}
