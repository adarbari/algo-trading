/**
 * The Watch button of an idea or a ticker page: adds the name to the watchlist, or takes it off
 * (ADR 0083, amendment 2026-11-01). Stores the instrument id only; a name cannot be added past
 * the cap, and a failed save says so (the entity puts the list back).
 */
import { Button, useToast } from '@algotrade/ui';

import {
  MAX_WATCHLIST,
  useSaveWatchlist,
  useTraderPreferences,
  type WatchedName,
} from '@/entities/trader-preferences';

export interface WatchToggleProps {
  instrumentId: string;
  /** The ticker, for the button's accessible name. */
  symbol: string;
}

export function WatchToggle({ instrumentId, symbol }: WatchToggleProps) {
  const prefs = useTraderPreferences();
  const save = useSaveWatchlist();
  const toast = useToast();
  const names: readonly WatchedName[] = prefs.data?.watchlist ?? [];
  const watching = names.some((n) => n.instrumentId === instrumentId);
  const full = !watching && names.length >= MAX_WATCHLIST;
  return (
    <Button
      size="sm"
      variant={watching ? 'primary' : 'secondary'}
      icon={watching ? 'check' : 'plus'}
      aria-pressed={watching}
      aria-label={`Watch ${symbol}`}
      disabled={prefs.data === undefined || full}
      onClick={() => {
        const next = watching
          ? names.filter((n) => n.instrumentId !== instrumentId)
          : [...names, { instrumentId, symbol }];
        save.mutate(next, {
          onError: () => {
            toast.show({ tone: 'warning', title: 'Watchlist not saved.' });
          },
        });
      }}
    >
      {watching ? 'Watching' : 'Watch'}
    </Button>
  );
}
