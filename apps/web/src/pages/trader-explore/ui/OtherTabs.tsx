/**
 * The Explore tabs other than Overview and Chart (Compare, Options, Features, Events, Screener
 * hits, Why it is an idea): one module the detail loads on demand, so Explore's first load
 * carries only the Overview and Chart widgets. A ticker named inside a panel opens in a tab of
 * its own.
 */
import { Stack } from '@algotrade/ui';

import { ComparePanel } from '@/widgets/compare-panel';
import { EventStudyPanel } from '@/widgets/event-study-panel';
import { EventsPanel } from '@/widgets/events-panel';
import { FeatureTable } from '@/widgets/feature-table';
import { FeaturesPanel } from '@/widgets/features-panel';
import { OptionsPanel } from '@/widgets/options-panel';
import { ScreenerHitsPanel, WhyIdeaPanel } from '@/widgets/screener-hits-panel';

import { DEFAULT_DIMENSIONS, joinList } from '@/entities/explore';
import { exploreState, openTicker } from '../model/state';
import type { DetailTabsProps } from './DetailTabs';

export function OtherTabs({ symbol, search, onSearchChange, onOpenScreener }: DetailTabsProps) {
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
      return <ScreenerHitsPanel symbol={symbol} onOpenScreener={onOpenScreener} via={state.via} />;
    case 'why':
      return state.via ? (
        <WhyIdeaPanel symbol={symbol} screenerId={state.via} onOpenScreener={onOpenScreener} />
      ) : null;
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
      return null;
  }
}
