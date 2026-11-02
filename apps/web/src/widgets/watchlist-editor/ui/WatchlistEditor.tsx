/**
 * The watchlist in Settings: a ticker search that adds a name, and the names as removable tags
 * (instrument ids are what is stored; up to 50). Stub for the design system's multiple
 * `Combobox` (C16): swap to it when it lands.
 */
import { Stack, TickerTag, useToast } from '@algotrade/ui';

import {
  MAX_WATCHLIST,
  useSaveWatchlist,
  useTraderPreferences,
  type WatchedName,
} from '@/entities/trader-preferences';
import { TickerSearch } from '@/features/ticker-search';

export function WatchlistEditor() {
  const prefs = useTraderPreferences();
  const save = useSaveWatchlist();
  const toast = useToast();
  const names: readonly WatchedName[] = prefs.data?.watchlist ?? [];
  const change = (next: readonly WatchedName[]) => {
    save.mutate(next, {
      onError: () => {
        toast.show({ tone: 'warning', title: 'Watchlist not saved.' });
      },
    });
  };
  return (
    <Stack gap={2}>
      {names.length < MAX_WATCHLIST ? (
        <TickerSearch
          chosen={names.flatMap((n) => (n.symbol ? [n.symbol] : []))}
          onChoose={(symbol, instrumentId) => {
            if (!names.some((n) => n.instrumentId === instrumentId)) {
              change([...names, { instrumentId, symbol }]);
            }
          }}
        />
      ) : null}
      <Stack direction="row" gap={1} wrap>
        {names.map((n) => (
          <TickerTag
            key={n.instrumentId}
            symbol={n.symbol ?? n.instrumentId}
            removeContext="from the watchlist"
            onRemove={() => {
              change(names.filter((x) => x.instrumentId !== n.instrumentId));
            }}
          />
        ))}
      </Stack>
    </Stack>
  );
}
