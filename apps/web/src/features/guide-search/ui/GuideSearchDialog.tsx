/**
 * The app's search dialog, opened by ⌘K from every page (ADR 0051, docs/ui/guide.md "Search";
 * the Evening Desk plan, V1): the design system's `SearchDialog` over two server reads. Tickers
 * come from the feature table's `q` filter (symbol or name over the whole universe); Setups are
 * the site setups of `Query.guideSearch` (its `edge` kind), opening the setup's page; every other
 * kind of the Guide follows under its own title and opens its page under /guide. The query is
 * sent about 200 ms after the last keystroke; the groups and their order are the server's.
 */
import { SearchDialog, type SearchDialogGroup } from '@algotrade/ui';
import { useState } from 'react';

import { useFeatureTable } from '@/entities/feature';
import { GUIDE_KIND_TITLES, guideEntryPath } from '@/entities/guide';
import { useDebounced } from '@/shared/lib';

import { useGuideSearchResults } from '../api/hooks';

/** How long the box waits after the last keystroke before the server is asked. */
export const SEARCH_DEBOUNCE_MS = 200;

/** Tickers listed in the dialog. */
export const TICKER_HITS = 6;
/** The Guide kind that is a setup of the Setups page, not a Guide page. */
const SETUP_KIND = 'edge';

export interface GuideSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open a page of the Guide (the app's navigation). */
  onNavigate: (path: string) => void;
}

export function GuideSearchDialog({ open, onOpenChange, onNavigate }: GuideSearchDialogProps) {
  const [query, setQuery] = useState('');
  const asked = useDebounced(query.trim(), SEARCH_DEBOUNCE_MS);
  const results = useGuideSearchResults(asked);
  const tickers = useFeatureTable({ columns: [], q: asked, size: TICKER_HITS }, asked !== '');
  const guide = (asked ? (results.data ?? []) : []).map((group): SearchDialogGroup => ({
    id: group.kind,
    title: group.kind === SETUP_KIND ? 'Setups' : (GUIDE_KIND_TITLES[group.kind] ?? group.kind),
    items: group.hits.map((hit) => ({
      id: hit.id,
      title: hit.title,
      snippet: hit.snippet,
      href:
        group.kind === SETUP_KIND
          ? `/edges?edge=${encodeURIComponent(hit.id)}`
          : guideEntryPath(hit.kind, hit.id),
    })),
  }));
  const tickerGroup: SearchDialogGroup[] =
    asked && (tickers.data?.rows.length ?? 0) > 0
      ? [
          {
            id: 'ticker',
            title: 'Tickers',
            items: (tickers.data?.rows ?? []).map((row) => ({
              id: row.symbol,
              title: row.symbol,
              snippet: row.name,
              href: `/explore?sel=${encodeURIComponent(row.symbol)}&focus=${encodeURIComponent(row.symbol)}`,
            })),
          },
        ]
      : [];
  const setups = guide.filter((g) => g.id === SETUP_KIND);
  const groups = [...tickerGroup, ...setups, ...guide.filter((g) => g.id !== SETUP_KIND)];
  const change = (next: boolean) => {
    if (!next) setQuery('');
    onOpenChange(next);
  };
  return (
    <SearchDialog
      open={open}
      onOpenChange={change}
      title="Search"
      placeholder="Search a ticker, a setup or the Guide"
      hint="Type a ticker, a setup or a word the app uses."
      query={query}
      onQueryChange={setQuery}
      groups={groups}
      loading={query.trim() !== asked || results.isFetching || tickers.isFetching}
      error={results.isError}
      onRetry={() => void results.refetch()}
      onSelect={(item) => {
        change(false);
        onNavigate(item.href);
      }}
    />
  );
}
