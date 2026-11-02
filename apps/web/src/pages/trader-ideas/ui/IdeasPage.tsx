/**
 * Trader > Ideas (home): the ideas of one tab,
 * per tab (Stocks | Premium, `?tab`): the picks of setups with a good stored verdict grouped by setup, beside a detail (ADR 0083); with no qualifying setup the tab shows its Unproven section, the screeners' matches with the paused picks and the shared filter bar. A row opens its ticker in Explore with the screener that surfaced it.
 */
import { Stack } from '@algotrade/ui';
import type { IdeaCompareSearch } from '@/features/idea-compare';
import { IdeasHeading } from '@/widgets/ideas-heading';
import { SetupIdeas } from '@/widgets/setup-ideas';
import { PausedIdeas } from '@/widgets/paused-ideas';
import { RegimeStrip } from '@/widgets/regime-strip';
import { TopIdeas, type TopIdeasSearch, type TopIdeasSearchPatch } from '@/widgets/top-ideas';

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
  /** Open a setup's page. */
  onOpenEdge: (edgeId: string) => void;
  /** Open a name's idea page under the setup that ranks it. */
  onOpenIdea: (symbol: string, setupId: string) => void;
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
  onOpenIdea,
}: IdeasPageProps) {
  const tab = search.tab ?? 'stocks';
  return (
    <Stack gap={3}>
      <IdeasHeading
        tab={tab}
        onTabChange={(next) => {
          onSearchChange({ tab: next === 'stocks' ? undefined : next });
        }}
      />
      <RegimeStrip onOpen={onOpenRegime} />
      <SetupIdeas
        tab={tab}
        onOpen={onOpen}
        onOpenEdge={onOpenEdge}
        onOpenIdea={onOpenIdea}
        unproven={
          <Stack gap={3}>
            <PausedIdeas tab={tab} onOpen={onOpen} onOpenScreener={onOpenScreener} />
            <TopIdeas
              tab={tab}
              search={search}
              onSearchChange={onSearchChange}
              onCompare={onCompare}
              onOpen={onOpen}
              onScreeners={onScreeners}
            />
          </Stack>
        }
      />
    </Stack>
  );
}
