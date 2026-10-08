/**
 * The Guide's search dialog (ADR 0051, docs/ui/guide.md "Search"): the design system's
 * `SearchDialog` over `Query.guideSearch`. The query is sent about 200 ms after the last
 * keystroke (the server reads the sources on every request); the results are the server's, in
 * its order, grouped by kind; a result opens the entry's page under /guide.
 */
import { SearchDialog, type SearchDialogGroup } from '@algotrade/ui';
import { useState } from 'react';

import { GUIDE_KIND_TITLES, guideEntryPath } from '@/entities/guide';
import { useDebounced } from '@/shared/lib';

import { useGuideSearchResults } from '../api/hooks';

/** How long the box waits after the last keystroke before the server is asked. */
export const SEARCH_DEBOUNCE_MS = 200;

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
  const groups: SearchDialogGroup[] = (asked ? (results.data ?? []) : []).map((group) => ({
    id: group.kind,
    title: GUIDE_KIND_TITLES[group.kind] ?? group.kind,
    items: group.hits.map((hit) => ({
      id: hit.id,
      title: hit.title,
      snippet: hit.snippet,
      href: guideEntryPath(hit.kind, hit.id),
    })),
  }));
  const change = (next: boolean) => {
    if (!next) setQuery('');
    onOpenChange(next);
  };
  return (
    <SearchDialog
      open={open}
      onOpenChange={change}
      title="Search the Guide"
      placeholder="Search fields, playbooks, terms and how-tos"
      hint="Type a field name, a playbook, or a word the app uses. Press Ctrl+K or ⌘K anywhere to open this."
      query={query}
      onQueryChange={setQuery}
      groups={groups}
      loading={query.trim() !== asked || results.isFetching}
      error={results.isError}
      onRetry={() => void results.refetch()}
      onSelect={(item) => {
        change(false);
        onNavigate(item.href);
      }}
    />
  );
}
