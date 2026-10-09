/**
 * The compare set: the open tickers, in the order they were opened, at most
 * six (one per chart series colour s1-s6). A ticker's colour is its position in the set.
 */
import type { Series } from '@algotrade/ui';

export const MAX_COMPARE = 6;

const SERIES: readonly Series[] = ['s1', 's2', 's3', 's4', 's5', 's6'];

/** The series colour of the ticker at `index` in the set. */
export function seriesAt(index: number): Series | undefined {
  return SERIES[index];
}

/** The series colour of `symbol` in `set` (undefined: not in it). */
export function seriesOf(set: readonly string[], symbol: string): Series | undefined {
  const index = set.indexOf(symbol);
  return index < 0 ? undefined : seriesAt(index);
}
