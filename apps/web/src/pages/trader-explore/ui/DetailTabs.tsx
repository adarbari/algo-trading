/**
 * The detail of Explore, the page's hero: the tabs of the ticker in focus (Overview, Compare,
 * Chart, Options, Features, Events, Screener hits, Why it is an idea), only the selected tab's
 * widget mounted. Compare is the rebased chart over the open tickers with their features side by
 * side (the feature table for those tickers, sorted in the table). A ticker named inside a panel
 * (a holding, a peer, a row of the comparison) opens in a tab of its own.
 */
import { Stack } from '@algotrade/ui';

import { ComparePanel } from '@/widgets/compare-panel';
import { EventStudyPanel } from '@/widgets/event-study-panel';
import { EventsPanel } from '@/widgets/events-panel';
import { FeatureTable } from '@/widgets/feature-table';
import { FeaturesPanel } from '@/widgets/features-panel';
import { HoldingsPanel } from '@/widgets/holdings-panel';
import { OptionsPanel } from '@/widgets/options-panel';
import { OverviewPanel } from '@/widgets/overview-panel';
import { PriceChartPanel } from '@/widgets/price-chart-panel';
import { ScreenerHitsPanel, WhyIdeaPanel } from '@/widgets/screener-hits-panel';

import { DEFAULT_DIMENSIONS, joinList, type ExploreSearch } from '@/entities/explore';
import { exploreState, openTicker, type SearchPatch } from '../model/state';

import { ExploreTabs } from './ExploreTabs';

export interface DetailTabsProps {
  /** The ticker in focus: the tabs are its own. */
  symbol: string;
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens one screener's results (the Screener hits and Why tabs). */
  onOpenScreener: (screenerId: string) => void;
}

function Content({ symbol, search, onSearchChange, onOpenScreener }: DetailTabsProps) {
  const state = exploreState(search);
  const open = (other: string) => {
    onSearchChange(openTicker(state, other));
  };
  switch (state.tab) {
    case 'compare':
      return (
        <Stack gap={4}>
          <ComparePanel
            symbols={state.open}
            range={state.range}
            onRangeChange={(range) => {
              onSearchChange({ range });
            }}
          />
          <FeatureTable
            label="Side by side"
            keys={state.open}
            columns={state.dimensions}
            onColumnsChange={(dims) => {
              onSearchChange({ dims: joinList(dims, DEFAULT_DIMENSIONS) });
            }}
            pickerLabel="Dimension"
            pickerIcon="plus"
            sortMode="client"
            emptyMessage="None of these tickers is in the reference snapshot."
            onRowActivate={open}
          />
        </Stack>
      );
    case 'hits':
      return <ScreenerHitsPanel symbol={symbol} onOpenScreener={onOpenScreener} />;
    case 'why':
      return state.via ? (
        <WhyIdeaPanel symbol={symbol} screenerId={state.via} onOpenScreener={onOpenScreener} />
      ) : null;
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
    case 'options':
      return (
        <OptionsPanel
          symbol={symbol}
          expiry={search.expiry ?? null}
          onExpiryChange={(expiry) => {
            onSearchChange({ expiry });
          }}
          view={search.view ?? 'simple'}
          onViewChange={(view) => {
            onSearchChange({ view: view === 'simple' ? undefined : view });
          }}
          right={search.right ?? 'P'}
          onRightChange={(right) => {
            onSearchChange({ right: right === 'P' ? undefined : right });
          }}
          allStrikes={search.strikes === 'all'}
          onAllStrikesChange={(all) => {
            onSearchChange({ strikes: all ? 'all' : undefined });
          }}
        />
      );
    case 'features':
      return (
        <FeaturesPanel
          symbol={symbol}
          feature={search.feature ?? null}
          onFeatureChange={(feature) => {
            onSearchChange({ feature });
          }}
        />
      );
    case 'events':
      return (
        <Stack gap={4}>
          <EventStudyPanel symbol={symbol} onSelectSymbol={open} />
          <EventsPanel symbol={symbol} />
        </Stack>
      );
    default:
      return (
        <OverviewPanel
          symbol={symbol}
          fund={<HoldingsPanel symbol={symbol} onSelectSymbol={open} />}
        />
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
