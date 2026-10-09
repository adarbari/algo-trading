/**
 * The detail of Explore, the page's hero: the tabs of the ticker in focus (Overview, Compare,
 * Chart, Options, Features, Events, Screener hits, Why it is an idea), only the selected tab's
 * widget mounted. Overview and Chart are in the page; the other tabs load on demand
 * (`OtherTabs`). A ticker named inside a panel (a holding, a peer, a row of the comparison)
 * opens in a tab of its own.
 */
import { Skeleton } from '@algotrade/ui';
import { Suspense } from 'react';

import { lazyPage } from '@/shared/lib/lazy';
import { HoldingsPanel } from '@/widgets/holdings-panel';
import { OverviewPanel } from '@/widgets/overview-panel';
import { PriceChartPanel } from '@/widgets/price-chart-panel';

import type { ExploreSearch } from '@/entities/explore';
import { exploreState, openTicker, type SearchPatch } from '../model/state';

import { ExploreTabs } from './ExploreTabs';

// The other tabs' widgets are one chunk, fetched when one of those tabs opens.
const OtherTabs = lazyPage(() => import('./OtherTabs'), 'OtherTabs');

export interface DetailTabsProps {
  /** The ticker in focus: the tabs are its own. */
  symbol: string;
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens one screener's results (the Screener hits and Why tabs). */
  onOpenScreener: (screenerId: string) => void;
}

function Content(props: DetailTabsProps) {
  const { symbol, search, onSearchChange } = props;
  const state = exploreState(search);
  switch (state.tab) {
    case 'chart':
      return (
        <PriceChartPanel
          symbol={symbol}
          range={state.range}
          onRangeChange={(range) => {
            onSearchChange({ range });
          }}
        />
      );
    case 'overview':
      return (
        <OverviewPanel
          symbol={symbol}
          fund={
            <HoldingsPanel
              symbol={symbol}
              onSelectSymbol={(other) => {
                onSearchChange(openTicker(state, other));
              }}
            />
          }
        />
      );
    default:
      return (
        <Suspense fallback={<Skeleton variant="rect" height="lg" label="Loading the tab" />}>
          <OtherTabs {...props} />
        </Suspense>
      );
  }
}

export function DetailTabs(props: DetailTabsProps) {
  const { open, tab, via } = exploreState(props.search);
  return (
    <ExploreTabs tab={tab} openCount={open.length} via={via} onSearchChange={props.onSearchChange}>
      <Content {...props} />
    </ExploreTabs>
  );
}
