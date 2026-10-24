/**
 * Explore with no ticker open: the whole universe as one table under the shared filter bar
 * (ADR 0082, surface `universe`). The filters in force are the page's `f` search param and are
 * counted and applied on the server before it pages; the column set is the compare dimensions
 * (`dims`); the sort is the table's own. A row opens its ticker; ticked rows (up to the open-tab
 * cap) open together as a compare set.
 */
import { Button, SearchInput, Stack, type DataTableSort } from '@algotrade/ui';
import { useEffect, useState } from 'react';

import { SurfaceFilterBar, SurfaceZeroResults, useFilterState } from '@/features/filter-bar';
import { termHelp } from '@/features/guide-help';
import { DEFAULT_DIMENSIONS, joinList } from '@/entities/explore';
import { FeatureTable } from '@/widgets/feature-table';

import { MAX_OPEN } from '../model/state';

/** The surface of the filter bar: its definitions are `config/site/filters/universe.toml`. */
const SURFACE = 'universe';
const SEARCH_DELAY_MS = 300;

export interface UniverseTableProps {
  /** The filter bar's `f` search param and its writer (the route's). */
  f: string | undefined;
  onFilterChange: (f: string | undefined) => void;
  /** The columns: catalogue names, as the URL's `dims` holds them. */
  columns: readonly string[];
  onColumnsChange: (dims: string | undefined) => void;
  /** Open one ticker. */
  onOpen: (symbol: string) => void;
  /** Open the ticked tickers as a compare set. */
  onCompare: (symbols: string[]) => void;
}

export function UniverseTable({
  f,
  onFilterChange,
  columns,
  onColumnsChange,
  onOpen,
  onCompare,
}: UniverseTableProps) {
  const filters = useFilterState(f, onFilterChange);
  const [sort, setSort] = useState<DataTableSort | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
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
  return (
    <FeatureTable
      label="Tickers"
      columns={columns}
      onColumnsChange={(dims) => {
        onColumnsChange(joinList(dims, DEFAULT_DIMENSIONS));
      }}
      filters={filters.filters}
      q={q}
      sortMode="server"
      sort={sort}
      onSortChange={setSort}
      selected={selected}
      onSelectedChange={setSelected}
      maxSelected={MAX_OPEN}
      onRowActivate={onOpen}
      emptyMessage={(facets) =>
        filters.filters.some((f) => f.active) ? (
          <SurfaceZeroResults surface={SURFACE} state={filters} facets={facets} />
        ) : q ? (
          `No ticker matches “${q}”`
        ) : (
          'No ticker in the universe.'
        )
      }
      header={(facets) => (
        <Stack gap={2}>
          <SurfaceFilterBar
            surface={SURFACE}
            state={filters}
            facets={facets}
            help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
            search={
              <SearchInput
                aria-label="Find a ticker"
                placeholder="Ticker or name…"
                value={text}
                onValueChange={setText}
              />
            }
          />
          {selected.length > 0 && (
            <Stack direction="row">
              <Button
                size="sm"
                onClick={() => {
                  onCompare(selected);
                }}
              >
                {selected.length === 1
                  ? 'Open selected'
                  : `Compare selected (${String(selected.length)})`}
              </Button>
            </Stack>
          )}
        </Stack>
      )}
    />
  );
}
