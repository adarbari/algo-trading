/**
 * The edges: one row each under its verdict (Works, Promising, Not working, Not enough data,
 * Waiting on data), with its screens, the out-of-sample result, the trades and where the user
 * stands; views (All, Mine, Following, Rejected) filter them, and the user's own files that do not
 * load are named with their reason.
 * Choosing a row (a click or Enter) opens the edge's page.
 */
import { Banner, DataTable, Panel, Stack, ViewChips, type DataTableGroupBy } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  EDGE_VIEWS,
  inView,
  useEdgeProblems,
  useEdges,
  verdictLabel,
  VERDICT_ORDER,
  type Edge,
  type EdgeView,
} from '@/entities/edge';

import { edgeColumns } from '../model/columns';

export interface EdgeListProps {
  /** Open the chosen edge's page. */
  onSelect: (id: string) => void;
  /** The view in use (a link keeps it); all when none. */
  view?: EdgeView;
  onViewChange?: (view: EdgeView) => void;
}

const GROUPS: DataTableGroupBy<Edge> = {
  getGroup: (e) => e.verdict.verdict,
  order: VERDICT_ORDER,
  label: (group, count) => `${verdictLabel(group)} · ${String(count)}`,
};

export function EdgeList({ onSelect, view = 'all', onViewChange }: EdgeListProps) {
  const edges = useEdges();
  const problems = useEdgeProblems();
  const columns = useMemo(() => edgeColumns(), []);
  const all = useMemo(() => edges.data ?? [], [edges.data]);
  const rows = useMemo(() => all.filter((e) => inView(e, view)), [all, view]);
  const state =
    edges.isError && !edges.data
      ? 'error'
      : edges.isPending
        ? 'loading'
        : all.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Stack gap={2}>
      {(problems.data ?? []).map((p) => (
        <Banner key={p.edgeId} tone="warning" title={`Left out: ${p.edgeId}`}>
          {p.reason}
        </Banner>
      ))}
      <ViewChips
        views={EDGE_VIEWS.map((v) => ({
          value: v.value,
          label: `${v.label} · ${String(all.filter((e) => inView(e, v.value)).length)}`,
        }))}
        value={view}
        onValueChange={(v) => {
          onViewChange?.(v);
        }}
      />
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
    </Stack>
  );
}
