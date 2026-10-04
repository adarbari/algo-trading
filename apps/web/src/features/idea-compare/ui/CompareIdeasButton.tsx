/** "Compare selected": opens the chosen tickers in Explore (the route turns the search into a URL). */
import { Button } from '@algotrade/ui';

import { compareSearch, MAX_COMPARE_IDEAS, type IdeaCompareSearch } from '../model/compare-search';

export interface CompareIdeasButtonProps {
  /** The chosen tickers, in pick order. */
  symbols: readonly string[];
  onCompare: (search: IdeaCompareSearch) => void;
}

export function CompareIdeasButton({ symbols, onCompare }: CompareIdeasButtonProps) {
  const search = compareSearch(symbols);
  const capped = symbols.length > MAX_COMPARE_IDEAS;
  return (
    <Button
      size="sm"
      variant="secondary"
      disabled={search === null}
      aria-label={
        capped
          ? `Compare the first ${MAX_COMPARE_IDEAS} of ${symbols.length} selected in Explore`
          : undefined
      }
      onClick={() => {
        if (search) onCompare(search);
      }}
    >
      {symbols.length > 0
        ? `Compare selected (${Math.min(symbols.length, MAX_COMPARE_IDEAS)})`
        : 'Compare selected'}
    </Button>
  );
}
