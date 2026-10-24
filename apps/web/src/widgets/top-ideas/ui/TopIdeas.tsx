/**
 * "Top ideas": one row per ticker with the screeners that picked it, ranked by the Ideas rule
 * (on the server: score, then consensus), under the shared filter bar (ADR 0082): the filters in
 * force are the page's `f` search param and narrow the whole list on the server before it is
 * paged; a change of filters starts again from the first page. Tick tickers to compare them in Explore, or click one to open it there
 * with the screener that surfaced it. The server sends the first page; "Show more" adds the next.
 */
import { Button, DataTable, Panel, SegmentedControl, ShowMore, Stack, Text } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  encodeFilters,
  SurfaceFilterBar,
  SurfaceZeroResults,
  useFilterState,
  type FilterSearch,
  type LabelOf,
} from '@/features/filter-bar';
import { ExportButton } from '@/features/filter-export';
import { GuideHelp, helped, termHelp } from '@/features/guide-help';
import { CompareIdeasButton, type IdeaCompareSearch } from '@/features/idea-compare';
import {
  IDEA_COLUMN_SETS,
  IDEAS_PAGE,
  useIdeas,
  type Idea,
  type IdeasSearch,
  type IdeasSearchPatch,
} from '@/entities/idea';
import { decisionLabel } from '@/entities/screen';

import { ideaColumns } from '../model/columns';

/** The surface of the filter bar: its definitions are `config/site/filters/ideas.toml`. */
const SURFACE = 'ideas';

/** The names of the stored values the definitions do not label: a decision's, a screener's. */
function labelsOf(screeners: readonly { id: string; name: string }[]): LabelOf {
  const names = new Map(screeners.map((s) => [s.id, s.name]));
  return (filterId, value) => {
    if (filterId === 'decision') return decisionLabel(value);
    return filterId === 'screener' ? names.get(value) : undefined;
  };
}

/** The page's search params: the column set and the filter bar's `f`. */
export type TopIdeasSearch = IdeasSearch & FilterSearch;
export type TopIdeasSearchPatch = IdeasSearchPatch & { f?: string | undefined };

export interface TopIdeasProps {
  /** The page's search params: the column set and the filters in force. */
  search: TopIdeasSearch;
  onSearchChange: (patch: TopIdeasSearchPatch) => void;
  onCompare: (search: IdeaCompareSearch) => void;
  /** Open a ticker in Explore, with the screener (config id) that surfaced it. */
  onOpen: (symbol: string, via: string) => void;
  /** Open the Screeners list (where a screener is run). */
  onScreeners: () => void;
}

export function TopIdeas({
  search,
  onSearchChange,
  onCompare,
  onOpen,
  onScreeners,
}: TopIdeasProps) {
  const filters = useFilterState(search.f, (f) => {
    onSearchChange({ f });
  });
  const ideas = useIdeas(filters.filters);
  const facets = ideas.data?.facets;
  const labelOf = useMemo(() => labelsOf(ideas.data?.screeners ?? []), [ideas.data?.screeners]);
  const [selected, setSelected] = useState<string[]>([]);
  const all = useMemo(() => ideas.data?.ideas ?? [], [ideas.data]);
  const columns = useMemo(() => ideaColumns(all, search.columns), [all, search.columns]);
  const symbols = selected.flatMap((id) => {
    const symbol = all.find((idea) => idea.instrumentId === id)?.symbol;
    return symbol ? [symbol] : [];
  });

  // Nothing stored yet (`ideas: null`), or no screener ran for the session (each NOT_RUN):
  // not an error, an empty panel that says so.
  const ran = ideas.data?.screeners.some((s) => s.notRun === null) ?? false;
  const state =
    ideas.isError && !ideas.data
      ? 'error'
      : ideas.isPending
        ? 'loading'
        : !ideas.data || ideas.data.session === null || !ran
          ? 'empty'
          : 'ready';

  const withheld = ideas.data?.screeners.filter((s) => s.withheld) ?? [];
  return (
    <Stack gap={3}>
      <SegmentedControl
        aria-label="Columns"
        size="sm"
        options={IDEA_COLUMN_SETS.map((c) => ({ value: c.id, label: c.label }))}
        value={search.columns ?? 'stocks'}
        onValueChange={(columns) => {
          onSearchChange({ columns });
        }}
      />
      <SurfaceFilterBar
        surface={SURFACE}
        views
        state={filters}
        facets={facets}
        help={(entry) =>
          entry.kind === 'term' ? (
            termHelp(entry.id)
          ) : entry.kind === 'field' ? (
            <GuideHelp entry={{ kind: 'field', id: entry.id }} />
          ) : null
        }
        labelOf={labelOf}
        actions={
          <ExportButton
            surface={SURFACE}
            f={encodeFilters(filters.filters)}
            session={ideas.data?.session}
            help={termHelp('export')}
          />
        }
      />
      <Panel
        title="Top ideas · across all your screeners"
        description={ideas.data?.session ? `Session ${ideas.data.session}` : undefined}
        flush
        state={state}
        loadingLabel="Loading ideas…"
        emptyMessage={
          <Stack gap={2} align="start">
            <Text tone="muted">
              {ideas.data?.session
                ? 'No screener has run for this session, so there are no ideas.'
                : 'No screener has run yet, so there are no ideas.'}
            </Text>
            <Button variant="primary" onClick={onScreeners}>
              Go to Screeners
            </Button>
          </Stack>
        }
        errorMessage="The ideas failed to load."
        onRetry={() => void ideas.refetch()}
        actions={
          <Stack direction="row" gap={2} align="center">
            <CompareIdeasButton symbols={symbols} onCompare={onCompare} />
            {termHelp('ideas_ranking')}
          </Stack>
        }
      >
        <Stack gap={2}>
          {withheld.length > 0 && (
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="muted">
                {`Withheld: ${withheld.map((s) => s.name).join(', ')}`}
              </Text>
              {termHelp('withheld_screener')}
            </Stack>
          )}
          <DataTable<Idea>
            label="Top ideas"
            columns={columns.map(helped)}
            rows={all}
            getRowId={(idea) => idea.instrumentId}
            getRowLabel={(idea) => idea.symbol ?? idea.instrumentId}
            defaultSort={{ columnId: 'rank', direction: 'asc' }}
            selectable
            selectedIds={selected}
            onSelectionChange={setSelected}
            onRowActivate={(idea) => {
              if (idea.symbol) onOpen(idea.symbol, idea.best.screenerId);
            }}
            canActivate={(idea) => Boolean(idea.symbol)}
            emptyMessage={
              filters.filters.some((f) => f.active) ? (
                <SurfaceZeroResults surface={SURFACE} state={filters} facets={facets} />
              ) : (
                'No screener picked anything in this session.'
              )
            }
            rowLines={search.columns === 'options' ? 2 : 3}
            visibleRows={14}
          />
          {state === 'ready' && ((ideas.data?.total ?? 0) > IDEAS_PAGE || ideas.data?.hasMore) && (
            <ShowMore
              shown={all.length}
              total={ideas.data?.total ?? 0}
              pageSize={IDEAS_PAGE}
              status={
                ideas.isFetchNextPageError ? 'error' : ideas.isFetchingNextPage ? 'loading' : 'idle'
              }
              onMore={() => void ideas.fetchNextPage()}
            />
          )}
        </Stack>
      </Panel>
    </Stack>
  );
}
