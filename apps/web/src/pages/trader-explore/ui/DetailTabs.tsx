/**
 * The detail side of Explore: the detail tabs (Overview, Compare,
 * Chart, Options, Features, Events, Screener hits; the Field guide takes the page, see
 * ExplorePage), each tab a widget for the compare set or
 * the focused ticker. Compare is the rebased chart over the compare set's features side by
 * side (the feature table for those tickers, sorted in the table).
 */
import { EmptyState, Stack } from '@algotrade/ui';

import { ComparePanel } from '@/widgets/compare-panel';
import { EventStudyPanel } from '@/widgets/event-study-panel';
import { EventsPanel } from '@/widgets/events-panel';
import { FeatureTable } from '@/widgets/feature-table';
import { FeaturesPanel } from '@/widgets/features-panel';
import { HoldingsPanel } from '@/widgets/holdings-panel';
import { OptionsPanel } from '@/widgets/options-panel';
import { OverviewPanel } from '@/widgets/overview-panel';
import { PriceChartPanel } from '@/widgets/price-chart-panel';
import { ScreenerHitsPanel } from '@/widgets/screener-hits-panel';

import { DEFAULT_DIMENSIONS, joinList, type ExploreSearch } from '../model/search';
import { exploreState, type SearchPatch } from '../model/state';

import { ExploreTabs } from './ExploreTabs';

export interface DetailTabsProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
  /** Opens one screener's results (the Screener hits tab). */
  onOpenScreener: (screenerId: string) => void;
}

function FocusedTab({ search, onSearchChange, symbol }: DetailTabsProps & { symbol: string }) {
  const { tab, range } = exploreState(search);
  switch (tab) {
    case 'overview':
      return (
        <OverviewPanel
          symbol={symbol}
          fund={
            <HoldingsPanel
              symbol={symbol}
              onSelectSymbol={(holding) => {
                onSearchChange({ focus: holding, expiry: undefined, feature: undefined });
              }}
            />
          }
        />
      );
    case 'chart':
      return (
        <PriceChartPanel
          symbol={symbol}
          range={range}
          onRangeChange={(r) => {
            onSearchChange({ range: r });
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
          <EventStudyPanel
            symbol={symbol}
            onSelectSymbol={(focus) => {
              onSearchChange({ focus, expiry: undefined, feature: undefined });
            }}
          />
          <EventsPanel symbol={symbol} />
        </Stack>
      );
    default:
      return null;
  }
}

export function DetailTabs({ search, onSearchChange, onOpenScreener }: DetailTabsProps) {
  const state = exploreState(search);
  const { selected, focused, tab } = state;
  let content;
  if (tab === 'compare') {
    const chart = (
      <ComparePanel
        symbols={selected}
        range={state.range}
        onRangeChange={(range) => {
          onSearchChange({ range });
        }}
      />
    );
    content =
      selected.length === 0 ? (
        chart
      ) : (
        <Stack gap={4}>
          {chart}
          <FeatureTable
            label="Side by side"
            keys={selected}
            columns={state.dimensions}
            onColumnsChange={(dims) => {
              onSearchChange({ dims: joinList(dims, DEFAULT_DIMENSIONS) });
            }}
            pickerLabel="Dimension"
            pickerIcon="plus"
            sortMode="client"
            emptyMessage="None of these tickers is in the reference snapshot."
            onRowActivate={(focus) => {
              onSearchChange({ focus, expiry: undefined, feature: undefined });
            }}
          />
        </Stack>
      );
  } else if (tab === 'hits' && focused) {
    content = <ScreenerHitsPanel symbol={focused} onOpenScreener={onOpenScreener} />;
  } else if (!focused) {
    content = (
      <EmptyState
        bordered
        icon="search"
        title="No ticker chosen"
        description="Click a row in the table (or tick tickers to compare) to see its detail here."
      />
    );
  } else {
    content = (
      <FocusedTab
        search={search}
        onSearchChange={onSearchChange}
        onOpenScreener={onOpenScreener}
        symbol={focused}
      />
    );
  }
  return (
    <ExploreTabs tab={tab} selectedCount={selected.length} onSearchChange={onSearchChange}>
      {content}
    </ExploreTabs>
  );
}
