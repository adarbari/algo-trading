/**
 * The screener runs, newest first, of any status, with the filter bar (user, screener, status;
 * the server applies them and the choice lives in the URL); choosing a row (a click or Enter)
 * selects it and the page shows its record beside the list. ADR 0082's definitions are not
 * served for this list yet, so the bar is the design system's `FilterBar` over the query's three
 * arguments. A text filter is sent on Enter or when the box loses focus.
 */
import {
  DataTable,
  Field,
  FilterBar,
  Input,
  Panel,
  SearchInput,
  Select,
  Stack,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  RUN_STATUSES,
  statusText,
  useScreenerRuns,
  type ScreenerRunFilters,
  type ScreenerRunSummary,
} from '@/entities/screener-run';
import { GuideHelp } from '@/features/guide-help';

import { runColumns } from '../model/columns';

const START_PAGE = 'read_screener_runs';
const ANY = '';

export interface ScreenerRunListProps {
  /** The chosen run's id (from the URL), or null. */
  selected: string | null;
  onSelect: (id: string) => void;
  /** The filters in force (from the URL). */
  filters?: ScreenerRunFilters;
  onFiltersChange?: (filters: ScreenerRunFilters) => void;
}

export function ScreenerRunList({
  selected,
  onSelect,
  filters = {},
  onFiltersChange,
}: ScreenerRunListProps) {
  const runs = useScreenerRuns(filters);
  const columns = useMemo(() => runColumns(), []);
  const [screener, setScreener] = useState(filters.screener ?? '');
  const [user, setUser] = useState(filters.user ?? '');
  const commit = (patch: ScreenerRunFilters) => {
    onFiltersChange?.({ ...filters, ...patch });
  };
  const rows = runs.data ?? [];
  const active = [filters.user, filters.screener, filters.status].filter(Boolean).length;
  const state =
    runs.isError && !runs.data
      ? 'error'
      : runs.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Stack gap={3}>
      <FilterBar
        label="Screener run filters"
        activeCount={active}
        {...(rows.length > 0 ? { count: `${String(rows.length)} runs` } : {})}
        search={
          <SearchInput
            aria-label="Screener"
            placeholder="Screener id"
            value={screener}
            onValueChange={setScreener}
            onSubmit={(value) => {
              commit({ screener: value.trim() || undefined });
            }}
          />
        }
        more={
          <Stack gap={3}>
            <Field label="User">
              <Input
                value={user}
                onValueChange={setUser}
                placeholder="site or a user"
                onBlur={() => {
                  commit({ user: user.trim() || undefined });
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') commit({ user: user.trim() || undefined });
                }}
              />
            </Field>
            <Field label="Status">
              <Select
                value={filters.status ?? ANY}
                onValueChange={(status) => {
                  commit({ status: RUN_STATUSES.find((s) => s === status) });
                }}
                options={[
                  { value: ANY, label: 'Any status' },
                  ...RUN_STATUSES.map((s) => ({ value: s, label: statusText(s) })),
                ]}
              />
            </Field>
          </Stack>
        }
      />
      <Panel
        title="Screener runs"
        flush
        state={state}
        loadingLabel="Loading screener runs…"
        emptyMessage={active > 0 ? 'No run matches these filters.' : 'No screener run is recorded.'}
        errorMessage="The screener runs failed to load."
        onRetry={() => void runs.refetch()}
        actions={<GuideHelp entry={{ kind: 'start', id: START_PAGE }} />}
      >
        <DataTable<ScreenerRunSummary>
          label="Screener runs"
          columns={columns}
          rows={rows}
          getRowId={(r) => r.runId}
          getRowLabel={(r) => `${r.configId} ${r.session} ${r.owner}`}
          activeRowId={selected}
          onRowActivate={(r) => {
            onSelect(r.runId);
          }}
          sortMode="client"
          emptyMessage="No screener run is recorded."
        />
      </Panel>
    </Stack>
  );
}
