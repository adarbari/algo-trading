/**
 * The compare set: the tickers selected in the table, in the order they were picked, at most
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

/**
 * The set after a table selection change: tickers still selected keep their place (and
 * colour), newly selected ones are appended in the given order, and the set is capped.
 */
export function nextSelection(current: readonly string[], selected: readonly string[]): string[] {
  const wanted = new Set(selected);
  const kept = current.filter((s) => wanted.has(s));
  const added = selected.filter((s) => !kept.includes(s));
  return [...kept, ...added].slice(0, MAX_COMPARE);
}
