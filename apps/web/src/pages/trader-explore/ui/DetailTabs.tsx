/**
 * The right-hand side of Explore: the compare bar and the detail tabs (Overview, Compare,
 * Chart, Options, Features, Events, Screener hits), each tab a widget for the compare set or
 * the focused ticker.
 */
import { EmptyState, Stack, Tabs, type TabItem } from '@algotrade/ui';

import { ComparePanel } from '@/widgets/compare-panel';
import { EventsPanel } from '@/widgets/events-panel';
import { FeaturesPanel } from '@/widgets/features-panel';
import { HoldingsPanel } from '@/widgets/holdings-panel';
import { OptionsPanel } from '@/widgets/options-panel';
import { OverviewPanel } from '@/widgets/overview-panel';
import { PriceChartPanel } from '@/widgets/price-chart-panel';
import { CompareSetBar } from '@/features/compare-set';

import { DEFAULT_DIMENSIONS, joinList, type ExploreSearch, type ExploreTab } from '../model/search';
import { defaultTab, exploreState, type SearchPatch } from '../model/state';

const TABS: readonly (TabItem & { id: ExploreTab })[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'compare', label: 'Compare' },
  { id: 'chart', label: 'Chart' },
  { id: 'options', label: 'Options' },
  { id: 'features', label: 'Features' },
  { id: 'events', label: 'Events' },
  { id: 'hits', label: 'Screener hits' },
];

export interface DetailTabsProps {
  search: ExploreSearch;
  onSearchChange: (patch: SearchPatch) => void;
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
      return <EventsPanel symbol={symbol} />;
    default:
      return null;
  }
}

export function DetailTabs({ search, onSearchChange }: DetailTabsProps) {
  const state = exploreState(search);
  const { selected, focused, tab } = state;
  const setSelected = (next: readonly string[]) => {
    onSearchChange({
      sel: next.length > 0 ? next.join(',') : undefined,
      focus: focused && next.includes(focused) ? search.focus : undefined,
    });
  };
  let content;
  if (tab === 'compare') {
    content = (
      <ComparePanel
        symbols={selected}
        range={state.range}
        onRangeChange={(range) => {
          onSearchChange({ range });
        }}
        dimensions={state.dimensions}
        onDimensionsChange={(dims) => {
          onSearchChange({ dims: joinList(dims, DEFAULT_DIMENSIONS) });
        }}
      />
    );
  } else if (tab === 'hits') {
    content = (
      <EmptyState
        bordered
        title="Screener hits"
        description="Which of your screeners flagged this ticker, when and why: coming with the screener engine."
      />
    );
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
    content = <FocusedTab search={search} onSearchChange={onSearchChange} symbol={focused} />;
  }
  return (
    <Stack gap={3}>
      <CompareSetBar
        symbols={selected}
        focused={focused}
        onRemove={(symbol) => {
          setSelected(selected.filter((s) => s !== symbol));
        }}
        onClear={() => {
          setSelected([]);
        }}
        onFocus={(symbol) => {
          onSearchChange({ focus: symbol, expiry: undefined, feature: undefined });
        }}
      />
      <Tabs
        label="View"
        items={TABS}
        value={tab}
        onChange={(id) => {
          onSearchChange({
            tab: id === defaultTab(selected.length) ? undefined : (id as ExploreTab),
          });
        }}
      >
        {content}
      </Tabs>
    </Stack>
  );
}
