/**
 * Explore's tab row for the ticker in focus (Overview, Compare when two or more tickers are
 * open, Chart, Options, Features, Events, Screener hits, and Why it is an idea when Ideas opened
 * the ticker; field help is the Guide, opened from each field's help button).
 */
import { Tabs, type TabItem } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { ExploreTab } from '@/entities/explore';
import type { SearchPatch } from '../model/state';

const TABS: readonly (TabItem & { id: ExploreTab })[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'compare', label: 'Compare' },
  { id: 'chart', label: 'Chart' },
  { id: 'options', label: 'Options' },
  { id: 'features', label: 'Features' },
  { id: 'events', label: 'Events' },
  { id: 'hits', label: 'Screener hits' },
  { id: 'why', label: 'Why it is an idea' },
];

export interface ExploreTabsProps {
  tab: ExploreTab;
  /** How many tickers are open: Compare needs two. */
  openCount: number;
  /** The screener that surfaced the ticker: the Why tab needs one. */
  via: string | null;
  onSearchChange: (patch: SearchPatch) => void;
  children: ReactNode;
}

export function ExploreTabs({ tab, openCount, via, onSearchChange, children }: ExploreTabsProps) {
  return (
    <Tabs
      label="View"
      items={TABS.filter(
        (t) => (t.id !== 'compare' || openCount > 1) && (t.id !== 'why' || via !== null),
      )}
      value={tab}
      onChange={(id) => {
        onSearchChange({ tab: id as ExploreTab });
      }}
    >
      {children}
    </Tabs>
  );
}
