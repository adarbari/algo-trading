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
  Panel,
  SearchInput,
  Stack,
  Text,
  type DataTableSort,
} from '@algotrade/ui';
import { useEffect, useMemo, useState } from 'react';

import { FeaturePicker } from '@/features/column-picker';
import { byName, useFeatureCatalogue } from '@/entities/feature';
import { decisionLabel } from '@/entities/idea';
import {
  orderedDecisions,
  runMessage,
  shownDecisions,
  useRunScreener,
  useSaveScreenerView,
  useScreenerView,
  useScreenTable,
  type ScreenChange,
  type ScreenTableRow,
} from '@/entities/screen';

import { resultColumns } from '../model/columns';

export interface ScreenerResultsProps {
  /** The screener whose latest run is shown. */
  id: string;
  /** Open a ticker in Explore. */
  onOpen: (symbol: string) => void;
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

export function ScreenerResults({ id, onOpen }: ScreenerResultsProps) {
  const view = useScreenerView(id);
  const save = useSaveScreenerView(id);
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
    save.mutate({
      columns: [...(next.columns ?? chosenColumns)],
      sort: formatSort(next.sort === undefined ? chosenSort : next.sort),
      decisions: [...(next.decisions ?? chosenDecisions)],
    });
  };

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
  const tableColumns = useMemo(() => (data ? resultColumns(data, known) : []), [data, known]);
  const rows: readonly ScreenTableRow[] = data?.page.items ?? [];
  const noRun = table.isError && !data;
  const state = noRun ? 'empty' : table.isError && !data ? 'error' : 'ready';

  return (
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
          onRowActivate={(row) => {
            if (row.symbol) onOpen(row.symbol);
          }}
          status={table.isPending ? 'loading' : 'ready'}
          emptyMessage={q ? `No ticker matches “${q}”` : 'No row has these decisions.'}
          toolbar={
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="muted">
                {data
                  ? `${count(data.page.total)} of ${count(Object.values(data.decisions).reduce((a, b) => a + b, 0))} rows`
                  : 'Loading rows…'}
              </Text>
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
  );
}
