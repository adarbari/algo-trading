/** Shares one chart window between the regime page's charts and its episodes table. */
import { useState, type ReactNode } from 'react';

import { DEFAULT_SELECTION, RangeContext, type RangeSelection } from '../model/range';

export function RegimeRangeProvider({ children }: { children: ReactNode }) {
  const state = useState<RangeSelection>(DEFAULT_SELECTION);
  return <RangeContext value={state}>{children}</RangeContext>;
}
