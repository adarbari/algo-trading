/**
 * The edges: one row each with its status, frozen period and canonical run. Choosing a row
 * (a click or Enter) selects it; the page shows its detail beside the list.
 */
import { DataTable, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import { useEdges, type Edge } from '@/entities/edge';

import { edgeColumns } from '../model/columns';

export interface EdgeListProps {
  /** The chosen edge's id (from the URL), or null. */
  selected: string | null;
  onSelect: (id: string) => void;
}

export function EdgeList({ selected, onSelect }: EdgeListProps) {
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
        activeRowId={selected}
        onRowActivate={(e) => {
          onSelect(e.id);
        }}
        defaultSort={{ columnId: 'name', direction: 'asc' }}
        emptyMessage="No edge is declared."
      />
    </Panel>
  );
}
