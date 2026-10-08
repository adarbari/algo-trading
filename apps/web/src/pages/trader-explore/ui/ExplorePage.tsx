/**
 * Trader > Explore: one page for the universe, instruments, chains and features. Left, the
 * ticker table (the feature table over the universe: filters, catalogue columns, sorting and
 * paging on the server, selection into the compare set); right, the detail tabs for the
 * compare bar and the detail tabs for the compare set and the focused ticker. On a phone the table
 * takes the width, the compare bar sits above it, and a chosen ticker's detail opens in a sheet
 * (MasterDetail). Every choice lives in the URL's search params (given as props by the route), so
 * a view is a shareable link.
 */
import { Heading, MasterDetail, Stack, Text } from '@algotrade/ui';

import { FeatureTable } from '@/widgets/feature-table';
import { MAX_COMPARE, nextSelection } from '@/features/compare-set';
import { TickerFilterBar, toTableFilters, type TickerFilters } from '@/features/ticker-filter';

import { DEFAULT_COLUMNS, formatSort, joinList, type ExploreSearch } from '../model/search';
import { exploreState, type SearchPatch } from '../model/state';

import { CompareBar } from './CompareBar';
import { DetailTabs } from './DetailTabs';

export interface ExplorePageProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens one screener's results (a name in the Screener hits tab). */
  onOpenScreener: (screenerId: string) => void;
}

export function ExplorePage({ search, onSearchChange, onOpenScreener }: ExplorePageProps) {
  const state = exploreState(search);
  const filters: TickerFilters = {
    q: search.q,
    type: search.type,
    sector: search.sector,
    liquidity: search.liq,
    leveraged: search.lev,
    optionable: search.opt,
  };
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Explore</Heading>
        <Text size="sm" tone="secondary">
          Every ticker with any feature from the catalogue: filter, pick columns, tick tickers to
          compare, click one for its chart, options, features and events.
        </Text>
      </Stack>
      <MasterDetail
        detailKey={search.focus ?? null}
        detailTitle={search.focus ?? ''}
        onDetailClose={() => {
          onSearchChange({ focus: undefined });
        }}
        summary={<CompareBar search={search} onSearchChange={onSearchChange} />}
        master={
          <FeatureTable
            label="Tickers"
            columns={state.columns}
            onColumnsChange={(cols) => {
              onSearchChange({ cols: joinList(cols, DEFAULT_COLUMNS) });
            }}
            narrowColumns={state.narrowColumns}
            onNarrowColumnsChange={(cols) => {
              onSearchChange({ ncols: joinList(cols) });
            }}
            filters={toTableFilters(filters)}
            header={
              <TickerFilterBar
                filters={filters}
                onChange={(f) => {
                  onSearchChange({
                    q: f.q,
                    type: f.type,
                    sector: f.sector,
                    liq: f.liquidity,
                    lev: f.leveraged,
                    opt: f.optionable,
                  });
                }}
              />
            }
            sortMode="server"
            sort={state.sort}
            onSortChange={(sort) => {
              onSearchChange({ sort: formatSort(sort) });
            }}
            selected={state.selected}
            onSelectedChange={(sel) => {
              const next = nextSelection(state.selected, sel);
              onSearchChange({ sel: next.length > 0 ? next.join(',') : undefined });
            }}
            maxSelected={MAX_COMPARE}
            onRowActivate={(focus) => {
              onSearchChange({ focus, expiry: undefined, feature: undefined });
            }}
            emptyMessage={
              search.q ? `No ticker matches “${search.q}”` : 'No tickers match these filters'
            }
          />
        }
        detail={
          <DetailTabs
            search={search}
            onSearchChange={onSearchChange}
            onOpenScreener={onOpenScreener}
          />
        }
      />
    </Stack>
  );
}
