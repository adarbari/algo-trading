/**
 * Trader > Explore: one page for the universe, instruments, chains and features. Left, the
 * ticker table (the feature table over the universe: filters, catalogue columns, sorting and
 * paging on the server, selection into the compare set); right, the detail tabs for the
 * compare set and the focused ticker. Every choice lives in the URL's search params (given as
 * props by the route), so a view is a shareable link.
 */
import { Grid, Heading, Stack, Text } from '@algotrade/ui';

import { FeatureTable } from '@/widgets/feature-table';
import { FieldGuide } from '@/widgets/field-guide';
import { MAX_COMPARE, nextSelection } from '@/features/compare-set';
import { TickerFilterBar, toTableFilters, type TickerFilters } from '@/features/ticker-filter';

import { DEFAULT_COLUMNS, formatSort, joinList, type ExploreSearch } from '../model/search';
import { exploreState, type SearchPatch } from '../model/state';

import { DetailTabs } from './DetailTabs';
import { ExploreTabs } from './ExploreTabs';

export interface ExplorePageProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens the Screener Builder (the field guide's "Add to a screen"). */
  onOpenBuilder: () => void;
}

export function ExplorePage({ search, onSearchChange, onOpenBuilder }: ExplorePageProps) {
  const state = exploreState(search);
  const filters: TickerFilters = {
    q: search.q,
    type: search.type,
    sector: search.sector,
    liquidity: search.liq,
    leveraged: search.lev,
    optionable: search.opt,
  };
  if (state.tab === 'guide') {
    return (
      <Stack gap={3}>
        <Stack gap={1}>
          <Heading level={1}>Explore</Heading>
          <Text size="sm" tone="secondary">
            Every catalogue field: what it means, how today&apos;s names are spread over it, and the
            criterion that reads it.
          </Text>
        </Stack>
        <ExploreTabs
          tab={state.tab}
          selectedCount={state.selected.length}
          onSearchChange={onSearchChange}
        >
          <FieldGuide
            theme={search.theme}
            field={search.field}
            symbol={search.symbol}
            defaultSymbol={state.focused}
            onThemeChange={(theme) => {
              onSearchChange({ theme, field: undefined });
            }}
            onFieldChange={({ theme, field }) => {
              onSearchChange({ theme, field });
            }}
            onSymbolChange={(symbol) => {
              onSearchChange({ symbol });
            }}
            onAddToScreen={onOpenBuilder}
          />
        </ExploreTabs>
      </Stack>
    );
  }
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
        <FeatureTable
          label="Tickers"
          columns={state.columns}
          onColumnsChange={(cols) => {
            onSearchChange({ cols: joinList(cols, DEFAULT_COLUMNS) });
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
        <DetailTabs search={search} onSearchChange={onSearchChange} />
      </Grid>
    </Stack>
  );
}
