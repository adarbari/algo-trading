/**
 * Trader > Explore: the ticker is the page. A search box adds a ticker (press / to jump to it);
 * open tickers are closable tabs, and the selected one's detail (overview, chart, options,
 * features, events, screener hits, and why Ideas surfaced it) takes the full width. Which
 * tickers are open, which is selected and what each tab shows live in the URL's search params
 * (given as props by the route), so a view is a shareable link.
 */
import { Heading, Skeleton, Stack, TabStrip } from '@algotrade/ui';
import { Suspense } from 'react';

import { TickerSearch } from '@/features/ticker-search';
import { lazyPage } from '@/shared/lib/lazy';

import type { ExploreSearch } from '@/entities/explore';
import {
  chooseTicker,
  closeTicker,
  exploreState,
  openTicker,
  type SearchPatch,
} from '../model/state';

import { DetailTabs } from './DetailTabs';

// The universe table (with the filter bar) is its own chunk: it loads only when no ticker is open.
const UniverseTable = lazyPage(() => import('./UniverseTable'), 'UniverseTable');

/** Fetch the universe table's chunk ahead of the page (a route loader), so it renders unsuspended. */
export const preloadUniverseTable = UniverseTable.preload;

export interface ExplorePageProps {
  /** Explore's state and, with no ticker open, the universe table's filters (`f`). */
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens one screener's results (a name in the Screener hits tab). */
  onOpenScreener: (screenerId: string) => void;
}

export function ExplorePage({ search, onSearchChange, onOpenScreener }: ExplorePageProps) {
  const state = exploreState(search);
  return (
    <Stack gap={3}>
      <Heading level={1}>Explore</Heading>
      <TickerSearch
        focusKey="/"
        chosen={state.open}
        onChoose={(symbol) => {
          onSearchChange(openTicker(state, symbol));
        }}
      />
      {state.focused ? (
        <TabStrip
          label="Open tickers"
          items={state.open.map((symbol) => ({
            id: symbol,
            label: symbol,
            mono: true,
            closeLabel: `Close ${symbol}`,
          }))}
          value={state.focused}
          onChange={(symbol) => {
            onSearchChange(chooseTicker(state, symbol));
          }}
          onClose={(symbol) => {
            onSearchChange(closeTicker(state, symbol));
          }}
        >
          <DetailTabs
            symbol={state.focused}
            search={search}
            onSearchChange={onSearchChange}
            onOpenScreener={onOpenScreener}
          />
        </TabStrip>
      ) : (
        <Suspense fallback={<Skeleton variant="rect" label="Loading the universe" />}>
          <UniverseTable
            f={search.f}
            onFilterChange={(f) => {
              onSearchChange({ f });
            }}
            columns={state.dimensions}
            onColumnsChange={(dims) => {
              onSearchChange({ dims });
            }}
            onOpen={(symbol) => {
              onSearchChange(openTicker(state, symbol));
            }}
            onCompare={(symbols) => {
              onSearchChange(
                symbols.length === 1 && symbols[0]
                  ? openTicker(state, symbols[0])
                  : { sel: symbols.join(','), focus: undefined, tab: 'compare' },
              );
            }}
          />
        </Suspense>
      )}
    </Stack>
  );
}
