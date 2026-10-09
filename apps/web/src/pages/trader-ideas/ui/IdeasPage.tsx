/**
 * Trader > Ideas (home): the ticker-level ideas table across the user's screeners, full width,
 * under the regime strip, the paused picks, the preset views and the filter chips (search
 * params). A row opens its ticker in Explore (or a compare set) with the screener that surfaced it.
 */
import { Stack } from '@algotrade/ui';

import type { IdeaCompareSearch } from '@/features/idea-compare';
import type { IdeasSearch, IdeasSearchPatch } from '@/entities/idea';
import { IdeasHeading } from '@/widgets/ideas-heading';
import { PausedIdeas } from '@/widgets/paused-ideas';
import { RegimeStrip } from '@/widgets/regime-strip';
import { TopIdeas } from '@/widgets/top-ideas';

export interface IdeasPageProps {
  /** The view in use and the filter chips (the URL's search params). */
  search: IdeasSearch;
  onSearchChange: (patch: IdeasSearchPatch) => void;
  /** Open the chosen tickers in Explore as a compare set. */
  onCompare: (search: IdeaCompareSearch) => void;
  /** Open one ticker in Explore, with the screener (config id) that surfaced it. */
  onOpen: (symbol: string, via: string) => void;
  /** Open the Screeners list. */
  onScreeners: () => void;
  /** Open one screener's results. */
  onOpenScreener: (screenerId: string) => void;
  /** Open the Regime page (the strip's chip). */
  onOpenRegime: () => void;
}

export function IdeasPage({
  search,
  onSearchChange,
  onCompare,
  onOpen,
  onScreeners,
  onOpenScreener,
  onOpenRegime,
}: IdeasPageProps) {
  return (
    <Stack gap={3}>
      <IdeasHeading />
      <RegimeStrip onOpen={onOpenRegime} />
      <PausedIdeas onOpen={onOpen} onOpenScreener={onOpenScreener} />
      <TopIdeas
        search={search}
        onSearchChange={onSearchChange}
        onCompare={onCompare}
        onOpen={onOpen}
        onOpenScreener={onOpenScreener}
        onScreeners={onScreeners}
      />
    </Stack>
  );
}
