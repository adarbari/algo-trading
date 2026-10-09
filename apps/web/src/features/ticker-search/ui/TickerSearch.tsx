/**
 * The ticker search: the design system's search combobox over the feature table's `q` filter
 * (the server matches the symbol or the name over the whole universe and returns a handful).
 * The query is sent about 200 ms after the last keystroke; choosing a result calls `onChoose`
 * with its symbol and clears the box. Tickers already chosen are marked "open".
 */
import { Combobox, type ComboboxOption } from '@algotrade/ui';
import { useState } from 'react';

import { useFeatureTable } from '@/entities/feature';
import { useDebounced } from '@/shared/lib';

/** How long the box waits after the last keystroke before the server is asked. */
export const SEARCH_DEBOUNCE_MS = 200;
/** Suggestions listed. */
export const SUGGESTIONS = 8;

export interface TickerSearchProps {
  /** A ticker was chosen. */
  onChoose: (symbol: string) => void;
  /** Tickers already chosen: their suggestion says so. */
  chosen?: readonly string[];
  /** The key that focuses the box from anywhere outside a text field. */
  focusKey?: string;
}

export function TickerSearch({ onChoose, chosen = [], focusKey }: TickerSearchProps) {
  const [typed, setTyped] = useState('');
  const asked = useDebounced(typed.trim(), SEARCH_DEBOUNCE_MS);
  const found = useFeatureTable(
    { columns: [], filters: { q: asked }, size: SUGGESTIONS },
    asked !== '',
  );
  const options: ComboboxOption[] = (asked ? (found.data?.rows ?? []) : []).map((row) => ({
    value: row.symbol,
    label: row.symbol,
    description: row.name,
    ...(chosen.includes(row.symbol) ? { badge: 'open' } : {}),
  }));
  return (
    <Combobox
      search
      mono
      filter="none"
      aria-label="Search tickers"
      placeholder="Search a ticker or company"
      {...(focusKey ? { focusKey } : {})}
      options={options}
      loading={typed.trim() !== asked || found.isFetching}
      {...(found.isError ? { error: 'The search failed' } : {})}
      emptyMessage={`No ticker matches “${asked}”`}
      onInputChange={setTyped}
      onValueChange={(symbol) => {
        if (symbol) onChoose(symbol);
        setTyped('');
      }}
    />
  );
}
