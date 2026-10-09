/**
 * Trader > Explore: the ticker is the page. A search box adds a ticker (press / to jump to it);
 * open tickers are closable tabs, and the selected one's detail (overview, chart, options,
 * features, events, screener hits, and why Ideas surfaced it) takes the full width. Which
 * tickers are open, which is selected and what each tab shows live in the URL's search params
 * (given as props by the route), so a view is a shareable link.
 */
import { EmptyState, Heading, Stack, TabStrip } from '@algotrade/ui';

import { TickerSearch } from '@/features/ticker-search';

import type { ExploreSearch } from '@/entities/explore';
import {
  chooseTicker,
  closeTicker,
  exploreState,
  openTicker,
  type SearchPatch,
} from '../model/state';

import { DetailTabs } from './DetailTabs';

export interface ExplorePageProps {
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
        <EmptyState
          bordered
          icon="search"
          title="No ticker open"
          description="Search for a ticker or company above to open it."
        />
      )}
    </Stack>
  );
}
