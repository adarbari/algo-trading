/**
 * The line an Ideas list shows while the viewer's watchlist filters it (ADR 0083 amendment (c)):
 * how many of the list's ideas are on the watchlist, its Guide help and the way to Settings to
 * change it. The counts are the server's; the help is the caller's (a Guide term).
 */
import { Button, Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

export interface WatchlistShowingProps {
  /** The ideas listed (the watched ones). */
  shown: number;
  /** The ideas the list held before the watchlist filtered it. */
  of: number;
  /** The Guide help of the filter. */
  help: ReactNode;
  /** Open Settings, where the watchlist is edited. */
  onEdit: () => void;
}

export function WatchlistShowing({ shown, of, help, onEdit }: WatchlistShowingProps) {
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <Text
        size="sm"
        tone="muted"
      >{`Showing ${String(shown)} of ${String(of)} ideas: your watchlist`}</Text>
      {help}
      <Button size="sm" variant="ghost" onClick={onEdit}>
        Edit watchlist
      </Button>
    </Stack>
  );
}
