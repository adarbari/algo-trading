/**
 * Trader > Explore: one page for the universe, instruments, chains and features. Left, the
 * ticker table (filters, catalogue columns, selection into the compare set); right, the
 * detail tabs for the compare set and the focused ticker. Every choice lives in the URL's
 * search params (given as props by the route), so a view is a shareable link.
 */
import { Grid, Heading, Stack, Text } from '@algotrade/ui';

import { TickerTable } from '@/widgets/ticker-table';

import { DEFAULT_COLUMNS, formatSort, joinList, type ExploreSearch } from '../model/search';
import { exploreState, type SearchPatch } from '../model/state';

import { DetailTabs } from './DetailTabs';

export interface ExplorePageProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
}

export function ExplorePage({ search, onSearchChange }: ExplorePageProps) {
  const state = exploreState(search);
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Explore</Heading>
        <Text size="sm" tone="secondary">
          Every ticker with any feature from the catalogue: filter, pick columns, tick tickers to
          compare, click one for its chart, options, features and events.
        </Text>
      </Stack>
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <TickerTable
          filters={{
            q: search.q,
            type: search.type,
            sector: search.sector,
            liquidity: search.liq,
            leveraged: search.lev,
            optionable: search.opt,
          }}
          onFiltersChange={(f) => {
            onSearchChange({
              q: f.q,
              type: f.type,
              sector: f.sector,
              liq: f.liquidity,
              lev: f.leveraged,
              opt: f.optionable,
            });
          }}
          columns={state.columns}
          onColumnsChange={(cols) => {
            onSearchChange({ cols: joinList(cols, DEFAULT_COLUMNS) });
          }}
          sort={state.sort}
          onSortChange={(sort) => {
            onSearchChange({ sort: formatSort(sort) });
          }}
          selected={state.selected}
          onSelectedChange={(sel) => {
            onSearchChange({ sel: sel.length > 0 ? sel.join(',') : undefined });
          }}
          onFocus={(focus) => {
            onSearchChange({ focus, expiry: undefined, feature: undefined });
          }}
        />
        <DetailTabs search={search} onSearchChange={onSearchChange} />
      </Grid>
    </Stack>
  );
}
