/**
 * Explore's typed state read from the search params, with the defaults filled in, and the URL
 * patches for opening, choosing and closing a ticker's tab (`sel` holds the open tickers in the
 * order they were opened, `focus` the one whose tab is selected).
 */
import type { ChartRange } from '@algotrade/ui';

import { MAX_COMPARE } from '@/features/compare-set';

import {
  DEFAULT_DIMENSIONS,
  splitList,
  type ExploreSearch,
  type ExploreTab,
} from '@/entities/explore';

/** A change to the search params; `undefined` removes a key. */
export type SearchPatch = { [K in keyof ExploreSearch]?: ExploreSearch[K] | undefined };

/** Tabs open at once: the compare chart gives each one of its series colours. */
export const MAX_OPEN = MAX_COMPARE;

export interface ExploreState {
  /** The open tickers, in the order they were opened (at most `MAX_OPEN`). */
  open: string[];
  focused: string | null;
  tab: ExploreTab;
  dimensions: readonly string[];
  range: ChartRange;
  /** The screener that surfaced the focused ticker (Ideas), when it did. */
  via: string | null;
}

/** The open list capped at `MAX_OPEN`: the oldest tabs give way, never `keep`. */
function capped(open: readonly string[], keep: string | null): string[] {
  const out = [...open];
  while (out.length > MAX_OPEN) {
    const drop = out.findIndex((symbol) => symbol !== keep);
    out.splice(drop, 1);
  }
  return out;
}

/** The tab shown when the URL names none: a set opened without a focus (a compare link) opens on
 * the comparison, anything else on the overview. */
function defaultTab(openCount: number, hasFocus: boolean): ExploreTab {
  return openCount > 1 && !hasFocus ? 'compare' : 'overview';
}

export function exploreState(search: ExploreSearch): ExploreState {
  const listed = splitList(search.sel);
  const focus = search.focus ?? null;
  const open = capped(focus && !listed.includes(focus) ? [...listed, focus] : listed, focus);
  const focused = focus && open.includes(focus) ? focus : (open[0] ?? null);
  const via = search.via ?? null;
  const wanted = search.tab ?? defaultTab(open.length, focus !== null);
  const tab =
    (wanted === 'compare' && open.length < 2) || (wanted === 'why' && !via) ? 'overview' : wanted;
  return {
    open,
    focused,
    tab,
    dimensions: search.dims === undefined ? DEFAULT_DIMENSIONS : splitList(search.dims),
    range: search.range ?? '1Y',
    via,
  };
}

const join = (open: readonly string[]) => (open.length > 0 ? open.join(',') : undefined);

/** What the ticker-specific choices (expiry, feature) and the surfacing screener reset to. */
const FRESH = { expiry: undefined, feature: undefined, via: undefined } as const;

/** Adds `symbol` to the open tabs (if it is not there) and selects it, on the overview. */
export function openTicker(state: ExploreState, symbol: string): SearchPatch {
  const open = state.open.includes(symbol) ? state.open : capped([...state.open, symbol], symbol);
  return { sel: join(open), focus: symbol, tab: undefined, ...FRESH };
}

/** Selects the tab of an open ticker, keeping the tab being viewed. */
export function chooseTicker(state: ExploreState, symbol: string): SearchPatch {
  return { sel: join(state.open), focus: symbol, ...FRESH };
}

/** Closes `symbol`'s tab; when it was selected, its right neighbour (else the left) is. */
export function closeTicker(state: ExploreState, symbol: string): SearchPatch {
  const at = state.open.indexOf(symbol);
  const open = state.open.filter((s) => s !== symbol);
  if (open.length === 0) return { sel: undefined, focus: undefined, tab: undefined, ...FRESH };
  if (symbol !== state.focused) return { sel: join(open), focus: state.focused ?? undefined };
  const next = open[Math.min(at, open.length - 1)];
  return { sel: join(open), focus: next, ...FRESH };
}
