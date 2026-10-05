/**
 * What an ETF holds, as Explore shows it: the largest holdings with their weights, how much of
 * the fund they are, the issuer's date and where the file came from. A holding links to its
 * Explore row only when its ticker is an instrument of the universe; cash, futures, bonds and
 * foreign lines keep their name only.
 */
import type { components } from '@/shared/api';

export type EtfHoldings = components['schemas']['EtfHoldings'];
export type Holding = components['schemas']['Holding'];

/** A holding as a table row. `symbol` is set only when the line links to an Explore row. */
export interface HoldingRow {
  id: string;
  rank: number;
  name: string;
  /** The issuer's ticker for the line (may not be in the universe). */
  ticker: string | null;
  /** The ticker of the Explore row this line opens; null when it is not in the universe. */
  symbol: string | null;
  /** Fraction of the fund (0.0844 = 8.44%). */
  weight: number;
  assetClass: string | null;
}

export function toRows(holdings: EtfHoldings): HoldingRow[] {
  return holdings.items.map((h) => ({
    id: String(h.rank),
    rank: h.rank,
    name: h.name,
    ticker: h.symbol,
    symbol: h.instrument_id !== null && h.symbol !== null ? h.symbol : null,
    weight: h.weight,
    assetClass: h.asset_class,
  }));
}

/** The share of the fund the listed holdings make up, by size (a fraction): a short or swap
 * line counts for how big it is, so an inverse fund does not read as negative. */
export function shownWeight(holdings: EtfHoldings): number {
  return holdings.items.reduce((sum, h) => sum + Math.abs(h.weight), 0);
}

/** Whether any listed line is short (a negative weight). */
export function hasShort(holdings: EtfHoldings): boolean {
  return holdings.items.some((h) => h.weight < 0);
}

const SOURCES: Readonly<Record<string, string>> = {
  ssga_holdings: 'State Street daily holdings file',
  ishares_holdings: 'iShares daily holdings file',
  sec_nport: 'SEC Form N-PORT filing (quarterly, filed about two months late)',
};

/** Where the holdings came from, in words; an unknown source is shown as its id. */
export function sourceLabel(source: string | null): string | null {
  if (source === null) return null;
  return SOURCES[source] ?? source;
}
