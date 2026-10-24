/**
 * A screener's results: its latest run as a review table (GraphQL `ScreenerRun.results`),
 * filtered, sorted and paged on the server. The shared filter bar (ADR 0082, surface
 * `screener_results`: decision, since the previous run, rank, score ...) filters it through the
 * page's `f` search param and the search box finds a ticker; the user's own catalogue columns,
 * sort and filters are their view of this screener (`features/table-view`: saved at once, never
 * part of the screener). The header says the regime the run stamped, and the picks the regime
 * gate paused are a decision of their own (PAUSED, reason in the row's detail).
 * A PARTIAL run says so with the tables it ran without, apart from the session's missing tables.
 * Enter on a row opens the ticker in Explore. With `renderDetail`, the row under review's detail
 * sits beside the table, or on a phone opens in a full-height sheet when a row is chosen
 * (MasterDetail), with previous / next and Open in Explore, Compare and Dismiss pinned below.
 */
import {
  ActionGroup,
  Button,
  MasterDetail,
  SearchInput,
  Stack,
  Text,
  type DataTableSort,
} from '@algotrade/ui';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import {
  encodeFilters,
  SurfaceFilterBar,
  SurfaceZeroResults,
  useFilterState,
  type LabelOf,
} from '@/features/filter-bar';
import { termHelp } from '@/features/guide-help';
import {
  formatSort,
  parseSort,
  screenerScope,
  useTableView,
  ViewControls,
} from '@/features/table-view';
import { UnknownNote } from '@/entities/availability';
import { useFilterSet } from '@/entities/filter';
import { byName, useFeatureCatalogue, type CriterionInfo, type TableRow } from '@/entities/feature';
import { RunRegimeChip } from '@/entities/regime';
import {
  DEFAULT_DECISIONS,
  decisionLabel,
  runMessage,
  useRunScreener,
  useScreenerResults,
} from '@/entities/screen';

import { usePageOf } from '../model/paging';
import { pageCount, resultsPlan } from '../model/plan';
import { resultRows } from '../model/rows';

import { TableFrame } from './TableFrame';

export interface ScreenerResultsProps {
  /** The screener whose latest run is shown. */
  id: string;
  /** The filter bar's `f` search param (the filters in force) and its writer (the route's). */
  f: string | undefined;
  onFilterChange: (f: string | undefined) => void;
  /** Open a ticker in Explore (Enter on the row under review). */
  onOpen: (symbol: string) => void;
  /** The row under review (instrument id); null or not in the page: the first row. */
  focusId: string | null;
  /** The row under review changed (a click, or j / k and the arrows); null: its sheet was closed (phone). */
  onFocusChange: (row: TableRow | null) => void;
  /** `c` on the row under review. */
  onToggleCompare: (row: TableRow) => void;
  /** `x` on the row under review: hide it for now. */
  onDismiss: (row: TableRow) => void;
  /** Instrument ids hidden for now. */
  dismissed: ReadonlySet<string>;
  onShowDismissed: () => void;
  /** Tickers (symbols) in the compare set: the sheet's Compare action says add or remove. */
  compared?: readonly string[];
  /** Tickers the unsaved criteria would drop from the picks (marked in the grid). */
  leaving?: ReadonlySet<string>;
  /** What to show beside the table for the row under review (its detail, chart, ...). */
  renderDetail?: (focus: {
    row: TableRow;
    criteria: readonly CriterionInfo[];
    /** Drawn in the phone sheet, whose footer carries the pick's actions. */
    inSheet: boolean;
  }) => ReactNode;
}

/** The surface of the filter bar: its definitions are `config/site/filters/screener_results.toml`. */
const SURFACE = 'screener_results';
const SEARCH_DELAY_MS = 300;
const PAGE_SIZE = 100;
const DEFAULT_SORT: DataTableSort = { columnId: 'rank', direction: 'asc' };
const count = (n: number) => n.toLocaleString('en-US');

/** A review opens on the picks, not the rejects (about 11k rows of misses). */
const picksFilter = (decisions: readonly string[]) =>
  encodeFilters([
    {
      id: 'decision',
      values: decisions.length > 0 ? [...decisions] : [...DEFAULT_DECISIONS],
      active: true,
    },
  ]);

/** The wording of a stored decision (the definition's options label the other values). */
const labelOf: LabelOf = (filterId, value) =>
  filterId === 'decision' ? decisionLabel(value) : undefined;

export function ScreenerResults({
  id,
  f,
  onFilterChange,
  onOpen,
  focusId,
  onFocusChange,
  onToggleCompare,
  onDismiss,
  dismissed,
  onShowDismissed,
  leaving,
  compared = [],
  renderDetail,
}: ScreenerResultsProps) {
  const definitions = useFilterSet(SURFACE);
  const known = definitions.data?.filterSet
    ? definitions.data.filterSet.filters.map((d) => d.id)
    : definitions.isError
      ? []
      : undefined;
  const view = useTableView(screenerScope(id), {
    f,
    onChange: onFilterChange,
    ...(known && { known }),
    fallback: picksFilter,
  });
  const filters = useFilterState(f, (next) => {
    onFilterChange(next);
    view.change({ filters: next ?? '', decisions: [] });
  });
  const runner = useRunScreener(id);
  const catalogue = useFeatureCatalogue();
  const featureNames = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(text);
    }, SEARCH_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [text]);

  const sort = parseSort(view.sort, DEFAULT_SORT);
  const asked = {
    filters: filters.filters,
    q,
    columns: view.columns,
    sort: formatSort(sort, DEFAULT_SORT) ?? undefined,
  };
  const [page, setPage] = usePageOf(JSON.stringify(asked));
  const results = useScreenerResults(id, { ...asked, page, size: PAGE_SIZE }, view.ready);
  const screener = results.data?.screener ?? null;
  const run = screener?.latestRun ?? null;
  const plan = useMemo(
    () =>
      resultsPlan({
        criteria: screener?.criteria ?? [],
        displayColumns: screener?.displayColumns ?? [],
        added: run?.results.columns ?? [],
        catalogue: featureNames,
        leaving,
        changes: true,
      }),
    [screener, run, featureNames, leaving],
  );
  const rows = useMemo(
    () => (run ? resultRows(run.results) : []).filter((row) => !dismissed.has(row.instrumentId)),
    [run, dismissed],
  );
  const focusRow = rows.find((row) => row.instrumentId === focusId) ?? rows[0] ?? null;
  const loaded = results.data !== undefined;
  const state = results.isError && !loaded ? 'error' : loaded && !run ? 'empty' : 'ready';
  const facets = run?.results.facets;

  const table = (
    <TableFrame
      panel={{
        title: 'Results',
        description: run
          ? `Run ${run.session}${run.previousSession ? ` · changes since ${run.previousSession}` : ''}`
          : undefined,
        actions: (
          <Stack direction="row" gap={2} align="center" wrap>
            {run ? <RunRegimeChip label={run.regime ?? null} /> : null}
            <Text size="sm" tone="muted">
              {runner.error ? 'The run could not be started' : runMessage(runner.run)}
            </Text>
            <Button size="sm" loading={runner.running} onClick={runner.start}>
              Run now
            </Button>
          </Stack>
        ),
        state,
        emptyMessage: screener
          ? `No run stored for this screener on ${results.data?.session?.date ?? 'the latest session'}. Run it now to see what it picks.`
          : 'No such screener.',
        errorMessage: 'The results failed to load.',
        onRetry: () => void results.refetch(),
      }}
      notes={
        results.data?.session && run
          ? {
              session: results.data.session.date,
              unavailable: [...results.data.session.unavailable, ...run.results.unavailable],
              preSnapshot: false,
              run: {
                session: run.session,
                partial: run.status === 'partial' || run.coverage === 'PARTIAL',
                unavailable: run.unavailable,
              },
            }
          : null
      }
      header={
        <Stack gap={2}>
          {screener?.notRun ? <UnknownNote unknown={screener.notRun} /> : null}
          <SurfaceFilterBar
            surface={SURFACE}
            state={filters}
            facets={facets}
            help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
            labelOf={labelOf}
            search={
              <SearchInput
                aria-label="Find a ticker"
                placeholder="Ticker or name…"
                value={text}
                onValueChange={setText}
                loading={results.isFetching}
              />
            }
          />
        </Stack>
      }
      summary={
        run
          ? `${count(run.results.total)} shown${facets ? ` · ${count(facets.total)} in the run` : ''}`
          : 'Loading rows…'
      }
      pager={
        run
          ? { page, pages: pageCount(run.results.total, run.results.size), onPage: setPage }
          : null
      }
      controls={
        <>
          {dismissed.size > 0 ? (
            <Button size="sm" variant="ghost" onClick={onShowDismissed}>
              {`${count(dismissed.size)} hidden · Show`}
            </Button>
          ) : null}
          <ViewControls view={view} />
          <FeaturePicker
            label="Add column"
            icon="plus"
            chosen={view.columns}
            onChange={(next) => {
              view.change({ columns: next });
            }}
          />
        </>
      }
      grid={{
        label: 'Screener results',
        columns: plan,
        rows,
        getRowId: (row) => row.instrumentId,
        visibleRows: 14,
        sort,
        sortMode: 'server',
        narrowColumns: view.narrowColumns,
        onNarrowColumnsChange: (next) => {
          view.change({ narrowColumns: next });
        },
        onSortChange: (next) => {
          view.change({ sort: formatSort(next, DEFAULT_SORT) });
        },
        activateOnClick: false,
        activeRowId: focusRow?.instrumentId ?? null,
        onActiveRowChange: onFocusChange,
        rowKeys: { c: onToggleCompare, x: onDismiss },
        onRowActivate: (row) => {
          onOpen(row.symbol);
        },
        status: results.isPending ? 'loading' : 'ready',
        emptyMessage: filters.filters.some((x) => x.active) ? (
          <SurfaceZeroResults surface={SURFACE} state={filters} facets={facets} />
        ) : q ? (
          `No ticker matches “${q}”`
        ) : (
          'This run has no rows.'
        ),
      }}
    />
  );
  if (!renderDetail) return table;
  // The sheet opens only for a row the user chose, not the first-row fallback.
  const chosen = focusRow !== null && focusRow.instrumentId === focusId ? focusId : null;
  const index = chosen === null ? -1 : rows.findIndex((row) => row.instrumentId === chosen);
  return (
    <MasterDetail
      columns="main-aside"
      master={table}
      detail={(inSheet) =>
        screener && focusRow
          ? renderDetail({ row: focusRow, criteria: screener.criteria, inSheet })
          : null
      }
      detailKey={chosen}
      detailTitle={focusRow?.symbol ?? ''}
      step={{
        hasPrevious: index > 0,
        hasNext: index >= 0 && index < rows.length - 1,
        onPrevious: () => {
          const row = rows[index - 1];
          if (row) onFocusChange(row);
        },
        onNext: () => {
          const row = rows[index + 1];
          if (row) onFocusChange(row);
        },
      }}
      detailFooter={
        focusRow ? (
          <ActionGroup
            label="Pick actions"
            actions={[
              {
                id: 'open',
                label: 'Open in Explore',
                icon: 'external',
                onClick: () => {
                  onOpen(focusRow.symbol);
                },
              },
              {
                id: 'compare',
                label: compared.includes(focusRow.symbol)
                  ? 'Remove from compare'
                  : 'Add to compare',
                icon: compared.includes(focusRow.symbol) ? 'minus' : 'plus',
                onClick: () => {
                  onToggleCompare(focusRow);
                },
              },
              {
                id: 'dismiss',
                label: 'Dismiss',
                icon: 'close',
                variant: 'ghost',
                onClick: () => {
                  onDismiss(focusRow);
                },
              },
            ]}
          />
        ) : null
      }
      onDetailClose={() => {
        onFocusChange(null);
      }}
    />
  );
}
