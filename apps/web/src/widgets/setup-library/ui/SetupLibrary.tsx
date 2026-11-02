/**
 * The setups library: Start here (the first three setups of the best verdict group, while the
 * list is not narrowed), then one row each under its verdict (Works, Promising, Not working, Not
 * enough data, Waiting on data), with its idea, the out-of-sample result (labelled backtested),
 * the trades and where the user stands; the shared filter bar (ADR 0082: owner, status, verdict, lift, live state, in the URL's
 * `f`) and a search over name and thesis narrow them on the server, and the user's own files that
 * do not load are named with their reason.
 * Choosing a row (a click or Enter) opens the edge's page.
 */
import {
  Banner,
  Button,
  DataTable,
  EmptyState,
  Panel,
  SearchInput,
  Stack,
  type DataTableGroupBy,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  useEdgeLiveStates,
  useEdgeProblems,
  useEdges,
  verdictLabel,
  VERDICT_ORDER,
  type EdgeRow,
} from '@/entities/edge';
import {
  SurfaceFilterBar,
  SurfaceZeroResults,
  useFilterState,
  type FilterSearch,
} from '@/features/filter-bar';
import { GuideHelp, termHelp } from '@/features/guide-help';
import { useDebounced } from '@/shared/lib';

import { edgeColumns } from '../model/columns';
import { StartHere } from './StartHere';

/** The surface of the filter bar: its definitions are `config/site/filters/edges.toml`. */
const SURFACE = 'edges';

/** The list's search params: the filter bar's `f` and the search text `q`. */
export type SetupLibrarySearch = FilterSearch & { q?: string };
export type SetupLibrarySearchPatch = { f?: string | undefined; q?: string | undefined };

export interface SetupLibraryProps {
  /** Open the chosen edge's page. */
  onSelect: (id: string) => void;
  /** The filters in force and the search text (the URL's search params). */
  search: SetupLibrarySearch;
  onSearchChange: (patch: SetupLibrarySearchPatch) => void;
}

const GROUPS: DataTableGroupBy<EdgeRow> = {
  getGroup: (e) => e.summary.verdict,
  order: VERDICT_ORDER,
  label: (group, count) => `${verdictLabel(group)} · ${String(count)}`,
};

export function SetupLibrary({ onSelect, search, onSearchChange }: SetupLibraryProps) {
  const filters = useFilterState(search.f, (f) => {
    onSearchChange({ f });
  });
  const text = search.q ?? '';
  const edges = useEdges(filters.filters, useDebounced(text, 250));
  const problems = useEdgeProblems();
  const live = useEdgeLiveStates();
  const columns = useMemo(
    () => edgeColumns(new Map((live.data ?? []).map((s) => [s.edgeId, s]))),
    [live.data],
  );
  const rows = useMemo(() => edges.data?.items ?? [], [edges.data]);
  const facets = edges.data?.facets;
  // Nothing declared (not the same as nothing matching: the facets' total is before the filters).
  const state =
    edges.isError && !edges.data
      ? 'error'
      : edges.isPending
        ? 'loading'
        : facets?.total === 0 && !text.trim()
          ? 'empty'
          : 'ready';
  const zero =
    filters.filters.length > 0 ? (
      <Stack gap={2} align="start">
        <SurfaceZeroResults surface={SURFACE} state={filters} facets={facets} />
        {text && (
          <ClearSearch
            onClear={() => {
              onSearchChange({ q: undefined });
            }}
          />
        )}
      </Stack>
    ) : (
      <EmptyState
        compact
        title={`No setup matches "${text}"`}
        action={
          <ClearSearch
            onClear={() => {
              onSearchChange({ q: undefined });
            }}
          />
        }
      />
    );
  const narrowed = filters.filters.length > 0 || text.trim() !== '';
  const best = useMemo(
    () =>
      [...rows].sort(
        (a, b) =>
          VERDICT_ORDER.indexOf(a.summary.verdict as (typeof VERDICT_ORDER)[number]) -
          VERDICT_ORDER.indexOf(b.summary.verdict as (typeof VERDICT_ORDER)[number]),
      ),
    [rows],
  );
  return (
    <Stack gap={3}>
      {!narrowed && <StartHere rows={best} hrefOf={(id) => `/edges?edge=${id}`} />}
      {(problems.data ?? []).map((p) => (
        <Banner
          key={p.edgeId}
          tone="warning"
          title={`Left out: ${p.edgeId}`}
          actions={termHelp('edge_left_out')}
        >
          {p.reason}
        </Banner>
      ))}
      <SurfaceFilterBar
        surface={SURFACE}
        views
        state={filters}
        facets={facets}
        help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
        search={
          <SearchInput
            aria-label="Find a setup"
            placeholder="Find a setup"
            value={text}
            onValueChange={(q) => {
              onSearchChange({ q: q || undefined });
            }}
          />
        }
      />
      <Panel
        title="Setups"
        flush
        actions={<GuideHelp entry={{ kind: 'start', id: 'read_an_edge_page' }} />}
        state={state}
        loadingLabel="Loading setups…"
        emptyMessage="No setup is published."
        errorMessage="The setups failed to load."
        onRetry={() => void edges.refetch()}
      >
        <DataTable<EdgeRow>
          label="Setups"
          columns={columns}
          rows={rows}
          getRowId={(e) => e.id}
          getRowLabel={(e) => e.name}
          onRowActivate={(e) => {
            onSelect(e.id);
          }}
          groupBy={GROUPS}
          rowLines={2}
          visibleRows="all"
          defaultSort={{ columnId: 'name', direction: 'asc' }}
          emptyMessage={zero}
        />
      </Panel>
    </Stack>
  );
}

function ClearSearch({ onClear }: { onClear: () => void }) {
  return (
    <Button size="sm" variant="secondary" onClick={onClear}>
      Clear the search
    </Button>
  );
}
