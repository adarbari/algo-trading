/**
 * A screener's results: its latest run as a review table. Decision chips (with the run's
 * counts) and New / Dropped chips filter it, the search box finds a ticker, and the user's own
 * catalogue columns, sort and decisions are saved as their view of this screener (never part
 * of the screener). Click a row to open the ticker in Explore.
 */
import {
  Box,
  Button,
  Chip,
  DataTable,
  Grid,
  Panel,
  SearchInput,
  Select,
  Stack,
  Text,
  type DataTableSort,
} from '@algotrade/ui';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { errorDetail } from '@/shared/api';

import { FeaturePicker } from '@/features/column-picker';
import { byName, useFeatureCatalogue } from '@/entities/feature';
import {
  orderedDecisions,
  decisionLabel,
  runMessage,
  shownDecisions,
  useDeleteScreenerView,
  useRunScreener,
  useSaveScreenerView,
  useScreenerView,
  useScreenTable,
  type ScreenChange,
  type ScreenTable,
  type ScreenTableRow,
} from '@/entities/screen';

import { resultColumns } from '../model/columns';

import { SaveViewDialog } from './SaveViewDialog';

export interface ScreenerResultsProps {
  /** The screener whose latest run is shown. */
  id: string;
  /** Open a ticker in Explore (Enter on the row under review). */
  onOpen: (symbol: string) => void;
  /** The row under review (instrument id); null or not in the list: the first row. */
  focusId: string | null;
  /** The row under review changed (a click, or j / k and the arrows). */
  onFocusChange: (row: ScreenTableRow) => void;
  /** `c` on the row under review. */
  onToggleCompare: (row: ScreenTableRow) => void;
  /** `x` on the row under review: hide it for now. */
  onDismiss: (row: ScreenTableRow) => void;
  /** Instrument ids hidden for now. */
  dismissed: ReadonlySet<string>;
  onShowDismissed: () => void;
  /** Symbols the unsaved criteria would drop from the picks (marked in the grid). */
  leaving?: ReadonlySet<string>;
  /** What to show beside the table for the row under review (its detail, chart, ...). */
  renderDetail?: (focus: { row: ScreenTableRow; table: ScreenTable }) => ReactNode;
}

const SEARCH_DELAY_MS = 300;
const DEFAULT_SORT: DataTableSort = { columnId: 'rank', direction: 'asc' };

/** `-criterion:iv30` -> the table's sort state; none or unknown -> rank. */
function parseSort(value: string | null | undefined): DataTableSort {
  if (!value) return DEFAULT_SORT;
  return value.startsWith('-')
    ? { columnId: value.slice(1), direction: 'desc' }
    : { columnId: value, direction: 'asc' };
}

const formatSort = (sort: DataTableSort | null): string | null =>
  sort === null || (sort.columnId === 'rank' && sort.direction === 'asc')
    ? null
    : `${sort.direction === 'desc' ? '-' : ''}${sort.columnId}`;

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
  const [viewName, setViewName] = useState<string | null>(null); // null: the default view
  const [savingAs, setSavingAs] = useState(false);
  const view = useScreenerView(id, viewName);
  const save = useSaveScreenerView(id);
  const remove = useDeleteScreenerView(id);
  const runner = useRunScreener(id);
  const catalogue = useFeatureCatalogue();
  const known = useMemo(() => byName(catalogue.data ?? []), [catalogue.data]);

  // The user's choices start from their saved view; any change is saved at once.
  const [columns, setColumns] = useState<readonly string[] | null>(null);
  const [sort, setSort] = useState<DataTableSort | null>(null);
  const [decisions, setDecisions] = useState<readonly string[] | null>(null);
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

  const chosenColumns = columns ?? view.data?.columns ?? [];
  const chosenSort = sort ?? parseSort(view.data?.sort);
  const chosenDecisions = decisions ?? shownDecisions(view.data);
  const persist = (next: {
    columns?: readonly string[];
    sort?: DataTableSort | null;
    decisions?: readonly string[];
  }) => {
    save.mutate({ name: viewName, view: currentView(next) });
  };
  const currentView = (next: Parameters<typeof persist>[0] = {}) => ({
    columns: [...(next.columns ?? chosenColumns)],
    sort: formatSort(next.sort === undefined ? chosenSort : next.sort),
    decisions: [...(next.decisions ?? chosenDecisions)],
  });
  /** Switch to another of your views: what you change next is saved into that one. */
  const selectView = (name: string | null) => {
    setViewName(name);
    setColumns(null);
    setSort(null);
    setDecisions(null);
  };
  const names = view.data?.names ?? [];

  const table = useScreenTable(
    id,
    {
      decisions: chosenDecisions,
      change,
      q,
      columns: chosenColumns,
      sort: formatSort(chosenSort) ?? undefined,
    },
    !view.isPending,
  );
  const data = table.data;
  const tableColumns = useMemo(
    () => (data ? resultColumns(data, known, leaving) : []),
    [data, known, leaving],
  );
  const rows = useMemo(
    () => (data?.page.items ?? []).filter((row) => !dismissed.has(row.instrument_id)),
    [data, dismissed],
  );
  const focusRow = rows.find((row) => row.instrument_id === focusId) ?? rows[0] ?? null;
  const noRun = table.isError && !data;
  const state = noRun ? 'empty' : table.isError && !data ? 'error' : 'ready';

  const results = (
    <>
      <SaveViewDialog
        key={String(savingAs)}
        open={savingAs}
        onOpenChange={setSavingAs}
        taken={names}
        saving={save.isPending}
        error={save.error ? errorDetail(save.error) : undefined}
        onSave={(name) => {
          save.mutate(
            { name, view: currentView() },
            {
              onSuccess: () => {
                setSavingAs(false);
                selectView(name);
              },
            },
          );
        }}
      />
      <Panel
        title="Results"
        description={
          data
            ? `Run ${data.session}${data.previous_session ? ` · changes since ${data.previous_session}` : ''}`
            : undefined
        }
        flush
        actions={
          <Stack direction="row" gap={2} align="center" wrap>
            <Text size="sm" tone="muted">
              {runner.error ? 'The run could not be started' : runMessage(runner.run)}
            </Text>
            <Button size="sm" loading={runner.running} onClick={runner.start}>
              Run now
            </Button>
          </Stack>
        }
        state={state}
        emptyMessage="No run stored for this screener yet. Run it now to see what it picks."
        errorMessage="The results failed to load."
        onRetry={() => void table.refetch()}
        footer={
          data && data.page.total > rows.length
            ? `Showing the first ${count(rows.length)} of ${count(data.page.total)} rows. Narrow the filters to see the rest.`
            : undefined
        }
      >
        <Stack gap={0}>
          <Box padding={3}>
            <Stack gap={2}>
              <SearchInput
                aria-label="Find a ticker"
                placeholder="Ticker or name…"
                value={text}
                onValueChange={setText}
                loading={table.isFetching}
              />
              <Stack direction="row" gap={1} wrap align="center">
                {orderedDecisions(data?.decisions ?? {}).map(({ decision, count: n }) => (
                  <Chip
                    key={decision}
                    label={`${decisionLabel(decision)} ${count(n)}`}
                    selected={chosenDecisions.includes(decision)}
                    onSelectedChange={(on) => {
                      const next = on
                        ? [...chosenDecisions, decision]
                        : chosenDecisions.filter((d) => d !== decision);
                      setDecisions(next);
                      persist({ decisions: next });
                    }}
                  />
                ))}
                {data && Object.keys(data.changes).length > 0
                  ? (['new', 'dropped'] as const).map((kind) => (
                      <Chip
                        key={kind}
                        label={`${kind === 'new' ? 'New' : 'Dropped'} ${count(data.changes[kind] ?? 0)}`}
                        selected={change === kind}
                        onSelectedChange={(on) => {
                          setChange(on ? kind : undefined);
                        }}
                      />
                    ))
                  : null}
              </Stack>
            </Stack>
          </Box>
          <DataTable<ScreenTableRow>
            label="Screener results"
            columns={tableColumns}
            rows={rows}
            getRowId={(row) => row.instrument_id}
            getRowLabel={(row) => row.symbol ?? row.instrument_id}
            rowLines={2}
            visibleRows={14}
            sort={chosenSort}
            onSortChange={(next) => {
              setSort(next);
              persist({ sort: next });
            }}
            activateOnClick={false}
            activeRowId={focusRow?.instrument_id ?? null}
            onActiveRowChange={onFocusChange}
            rowKeys={{ c: onToggleCompare, x: onDismiss }}
            onRowActivate={(row) => {
              if (row.symbol) onOpen(row.symbol);
            }}
            status={table.isPending ? 'loading' : 'ready'}
            emptyMessage={q ? `No ticker matches “${q}”` : 'No row has these decisions.'}
            toolbar={
              <Stack direction="row" gap={2} align="center" wrap>
                <Text size="sm" tone="muted">
                  {data
                    ? `${count(data.page.total)} shown · ${count(Object.values(data.decisions).reduce((a, b) => a + b, 0))} in the run`
                    : 'Loading rows…'}
                </Text>
                {dismissed.size > 0 ? (
                  <Button size="sm" variant="ghost" onClick={onShowDismissed}>
                    {`${count(dismissed.size)} hidden · Show`}
                  </Button>
                ) : null}
                <Select
                  aria-label="View"
                  size="sm"
                  width="auto"
                  value={viewName ?? ''}
                  options={[
                    { value: '', label: 'Default view' },
                    ...names.map((n) => ({ value: n, label: n })),
                  ]}
                  onValueChange={(value) => {
                    selectView(value === '' ? null : value);
                  }}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setSavingAs(true);
                  }}
                >
                  Save view as…
                </Button>
                {viewName !== null ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={remove.isPending}
                    onClick={() => {
                      remove.mutate(viewName, {
                        onSuccess: () => {
                          selectView(null);
                        },
                      });
                    }}
                  >
                    Delete view
                  </Button>
                ) : null}
                <FeaturePicker
                  label="Add column"
                  icon="plus"
                  chosen={chosenColumns}
                  onChange={(next) => {
                    setColumns(next);
                    persist({ columns: next });
                  }}
                />
              </Stack>
            }
          />
        </Stack>
      </Panel>
    </>
  );
  if (!renderDetail) return results;
  return (
    <Grid columns="main-aside" gap={4} collapse="lg" align="start">
      {results}
      {data && focusRow ? renderDetail({ row: focusRow, table: data }) : null}
    </Grid>
  );
}
