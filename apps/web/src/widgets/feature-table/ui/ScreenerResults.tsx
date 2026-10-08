/**
 * A screener's results: its latest run as a review table (GraphQL `ScreenerRun.results`),
 * filtered, sorted and paged on the server. Decision chips (with the run's counts) and New /
 * Dropped chips filter it, the search box finds a ticker, and the user's own catalogue
 * columns, sort and decisions are their view of this screener (`features/table-view`: saved at
 * once, never part of the screener). The header says the regime the run stamped, and the picks
 * the regime gate paused are a decision chip of their own (PAUSED, reason in the row's detail).
 * A PARTIAL run says so with the tables it ran without, apart from the session's missing tables.
 * Enter on a row opens the ticker in Explore. With `renderDetail`, the row under review's detail
 * sits beside the table, or on a phone opens in a sheet when a row is chosen (MasterDetail).
 */
import {
  Button,
  Chip,
  MasterDetail,
  SearchInput,
  Stack,
  Text,
  type DataTableSort,
} from '@algotrade/ui';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import {
  formatSort,
  parseSort,
  screenerScope,
  useTableView,
  ViewControls,
} from '@/features/table-view';
import { byName, useFeatureCatalogue, type CriterionInfo, type TableRow } from '@/entities/feature';
import { RunRegimeChip } from '@/entities/regime';
import {
  DEFAULT_DECISIONS,
  decisionLabel,
  orderedDecisions,
  runMessage,
  useRunScreener,
  useScreenerResults,
  type ScreenChange,
} from '@/entities/screen';

import { usePageOf } from '../model/paging';
import { pageCount, resultsPlan } from '../model/plan';
import { resultRows } from '../model/rows';

import { TableFrame } from './TableFrame';

export interface ScreenerResultsProps {
  /** The screener whose latest run is shown. */
  id: string;
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
  /** Tickers the unsaved criteria would drop from the picks (marked in the grid). */
  leaving?: ReadonlySet<string>;
  /** What to show beside the table for the row under review (its detail, chart, ...). */
  renderDetail?: (focus: { row: TableRow; criteria: readonly CriterionInfo[] }) => ReactNode;
}

const SEARCH_DELAY_MS = 300;
const PAGE_SIZE = 100;
const DEFAULT_SORT: DataTableSort = { columnId: 'rank', direction: 'asc' };
const count = (n: number) => n.toLocaleString('en-US');

export function ScreenerResults({
  id,
  onOpen,
  focusId,
  onFocusChange,
  onToggleCompare,
  onDismiss,
  dismissed,
  onShowDismissed,
  leaving,
  renderDetail,
}: ScreenerResultsProps) {
  const view = useTableView(screenerScope(id));
  const runner = useRunScreener(id);
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);
  const [change, setChange] = useState<ScreenChange | undefined>(undefined);
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
  const decisions = view.decisions ?? DEFAULT_DECISIONS;
  const asked = {
    decisions,
    change,
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
        catalogue: known,
        leaving,
        changes: true,
      }),
    [screener, run, known, leaving],
  );
  const rows = useMemo(
    () => (run ? resultRows(run.results) : []).filter((row) => !dismissed.has(row.instrumentId)),
    [run, dismissed],
  );
  const focusRow = rows.find((row) => row.instrumentId === focusId) ?? rows[0] ?? null;
  const loaded = results.data !== undefined;
  const state = results.isError && !loaded ? 'error' : loaded && !run ? 'empty' : 'ready';
  const inRun = run ? run.decisions.reduce((sum, d) => sum + d.count, 0) : 0;
  const changes = new Map((run?.changes ?? []).map((c) => [c.change, c.count]));

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
              missing: [...results.data.session.missing, ...run.results.missing],
              preSnapshot: false,
              run: {
                session: run.session,
                partial: run.status === 'partial' || run.coverage === 'PARTIAL',
                missing: run.missingTables,
              },
            }
          : null
      }
      header={
        <Stack gap={2}>
          <SearchInput
            aria-label="Find a ticker"
            placeholder="Ticker or name…"
            value={text}
            onValueChange={setText}
            loading={results.isFetching}
          />
          <Stack direction="row" gap={1} wrap align="center">
            {orderedDecisions(run?.decisions ?? []).map(({ decision, count: n }) => (
              <Chip
                key={decision}
                label={`${decisionLabel(decision)} ${count(n)}`}
                selected={decisions.includes(decision)}
                onSelectedChange={(on) => {
                  view.change({
                    decisions: on
                      ? [...decisions, decision]
                      : decisions.filter((d) => d !== decision),
                  });
                }}
              />
            ))}
            {changes.size > 0
              ? (['new', 'dropped'] as const).map((kind) => (
                  <Chip
                    key={kind}
                    label={`${kind === 'new' ? 'New' : 'Dropped'} ${count(changes.get(kind) ?? 0)}`}
                    selected={change === kind}
                    onSelectedChange={(on) => {
                      setChange(on ? kind : undefined);
                    }}
                  />
                ))
              : null}
          </Stack>
        </Stack>
      }
      summary={
        run ? `${count(run.results.total)} shown · ${count(inRun)} in the run` : 'Loading rows…'
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
        emptyMessage: q ? `No ticker matches “${q}”` : 'No row has these decisions.',
      }}
    />
  );
  if (!renderDetail) return table;
  // The sheet opens only for a row the user chose, not the first-row fallback.
  const chosen = focusRow !== null && focusRow.instrumentId === focusId ? focusId : null;
  return (
    <MasterDetail
      columns="main-aside"
      master={table}
      detail={
        screener && focusRow ? renderDetail({ row: focusRow, criteria: screener.criteria }) : null
      }
      detailKey={chosen}
      detailTitle={focusRow?.symbol ?? ''}
      onDetailClose={() => {
        onFocusChange(null);
      }}
    />
  );
}
