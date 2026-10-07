/**
 * Explore's tab row (Overview, Compare, Chart, Options, Features, Events, Screener hits, and the
 * Field guide), shared by the ticker detail and the field guide, which takes the whole page.
 * Choosing the default tab for the compare set removes `tab` from the URL.
 */
import { Tabs, type TabItem } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { ExploreTab } from '../model/search';
import { defaultTab, type SearchPatch } from '../model/state';

const TABS: readonly (TabItem & { id: ExploreTab })[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'compare', label: 'Compare' },
  { id: 'chart', label: 'Chart' },
  { id: 'options', label: 'Options' },
  { id: 'features', label: 'Features' },
  { id: 'events', label: 'Events' },
  { id: 'hits', label: 'Screener hits' },
  { id: 'guide', label: 'Field guide' },
];

export interface ExploreTabsProps {
  tab: ExploreTab;
  /** How many tickers are in the compare set (the default tab depends on it). */
  selectedCount: number;
  onSearchChange: (patch: SearchPatch) => void;
  children: ReactNode;
}

export function ExploreTabs({ tab, selectedCount, onSearchChange, children }: ExploreTabsProps) {
  return (
    <Tabs
      label="View"
      items={TABS}
      value={tab}
      onChange={(id) => {
        onSearchChange({ tab: id === defaultTab(selectedCount) ? undefined : (id as ExploreTab) });
      }}
    >
      {children}
    </Tabs>
  );
}
