/**
 * Trader > Ideas (home): the ticker-level ideas table across the user's screeners, full width,
 * under the regime strip, the paused picks and the shared filter bar (search params). A row opens its ticker in Explore (or a compare set) with the screener that surfaced it.
 * The signals of the followed edges sit above the table and load on demand (their own chunk).
 */
import { Stack } from '@algotrade/ui';
import { Suspense } from 'react';

import { lazyPage } from '@/shared/lib/lazy';
import type { IdeaCompareSearch } from '@/features/idea-compare';
import { IdeasHeading } from '@/widgets/ideas-heading';
import { PausedIdeas } from '@/widgets/paused-ideas';
import { RegimeStrip } from '@/widgets/regime-strip';
import { TopIdeas, type TopIdeasSearch, type TopIdeasSearchPatch } from '@/widgets/top-ideas';

const EdgeSignals = lazyPage(() => import('@/widgets/edge-signals'), 'EdgeSignals');

/** Fetch the edge signals' chunk ahead of the page (a route loader), so it renders unsuspended. */
export const preloadEdgeSignals = EdgeSignals.preload;

export interface IdeasPageProps {
  /** The column set and the filters in force (the URL's search params). */
  search: TopIdeasSearch;
  onSearchChange: (patch: TopIdeasSearchPatch) => void;
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
  /** Open an edge's page (a followed edge's row). */
  onOpenEdge: (edgeId: string) => void;
  /** Open the Edges list (where an edge is followed). */
  onOpenEdges: () => void;
}

export function IdeasPage({
  search,
  onSearchChange,
  onCompare,
  onOpen,
  onScreeners,
  onOpenScreener,
  onOpenRegime,
  onOpenEdge,
  onOpenEdges,
}: IdeasPageProps) {
  return (
    <Stack gap={3}>
      <IdeasHeading />
      <RegimeStrip onOpen={onOpenRegime} />
      <Suspense fallback={null}>
        <EdgeSignals onOpen={onOpen} onOpenEdge={onOpenEdge} onOpenEdges={onOpenEdges} />
      </Suspense>
      <PausedIdeas onOpen={onOpen} onOpenScreener={onOpenScreener} />
      <TopIdeas
        search={search}
        onSearchChange={onSearchChange}
        onCompare={onCompare}
        onOpen={onOpen}
        onScreeners={onScreeners}
      />
    </Stack>
  );
}
