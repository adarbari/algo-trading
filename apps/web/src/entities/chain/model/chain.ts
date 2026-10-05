/**
 * One underlying's option chain shaped for the Options view: the rows of one expiry and right
 * (puts or calls), the 8-15 delta band short-premium sellers look at, and a plain-English line
 * per contract ("Get paid $820 now; buy 100 AAPL at $325 if it falls ~2.6% by 20 Nov").
 *
 * Every date fact comes from the server: each expiry's `days` from the session, the target
 * expiry and the underlying's price as catalogue features (`CHAIN_FEATURES`).
 */
import { formatValue } from '@algotrade/ui';

import { feature, type gqlTypes } from '@/shared/api';

type ChainInstrument = NonNullable<gqlTypes.OptionChainQuery['instrument']>;
export type OptionChain = NonNullable<ChainInstrument['chain']>;
export type OptionExpiry = OptionChain['expiries'][number];
export type OptionQuote = NonNullable<
  NonNullable<gqlTypes.OptionQuotesQuery['instrument']>['chain']
>['quotes'][number];
export type OptionRight = 'P' | 'C';

/** The per-instrument facts the Options view shows with the chain. */
export const CHAIN_FACTS = {
  target: feature('rollup.option_liquidity@v1.target_expiry'),
  spot: feature('rollup.option_liquidity@v1.underlying_price'),
  iv30: feature('rollup.iv30@v1.iv30'),
} as const;

export const CHAIN_FEATURES = Object.values(CHAIN_FACTS);

/** The chain facts the server sent (null: UNKNOWN for the session, or not that type). */
export interface ChainFacts {
  /** The expiry the liquidity rollup targets (ISO day). */
  target: string | null;
  /** The underlying's price captured with the chain. */
  spot: number | null;
  /** Our 30-day implied volatility (a fraction). */
  iv30: number | null;
}

export function chainFacts(
  features: readonly { name: string; value?: unknown }[] | undefined,
): ChainFacts {
  const of = (name: string) => features?.find((f) => f.name === name)?.value;
  const target = of(CHAIN_FACTS.target);
  return {
    target: typeof target === 'string' ? target : null,
    spot: n(of(CHAIN_FACTS.spot)),
    iv30: n(of(CHAIN_FACTS.iv30)),
  };
}

/** |delta| from 0.08 to 0.15: the band highlighted in the chain. */
export const DELTA_BAND: readonly [number, number] = [0.08, 0.15];

/** Strikes within this share of the spot count as "near the money". */
export const NEAR_MONEY = 0.25;

export interface ChainRow {
  id: string;
  strike: number;
  bid: number | null;
  ask: number | null;
  last: number | null;
  volume: number | null;
  openInterest: number | null;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  inBand: boolean;
  plain: string;
}

export function inDeltaBand(delta: number | null | undefined): boolean {
  if (delta === null || delta === undefined) return false;
  const size = Math.abs(delta);
  return size >= DELTA_BAND[0] && size <= DELTA_BAND[1];
}

const money = (value: number, digits = 0) => formatValue(value, { kind: 'currency', digits }).text;
const strikeText = (strike: number) => money(strike, Number.isInteger(strike) ? 0 : 2);

/** One contract in words, for a reader who sells options for income. */
export function plainEnglish(
  right: OptionRight,
  quote: { strike: number; bid: number | null },
  spot: number | null,
  symbol: string,
  expiry: string,
): string {
  const strike = strikeText(quote.strike);
  const kind = right === 'P' ? 'put' : 'call';
  if (!quote.bid || quote.bid <= 0) return `No bid: nobody pays for this ${kind} today`;
  if (spot === null) return `Get paid ${money(quote.bid * 100)} now for this ${kind}`;
  const by = formatValue(expiry, { kind: 'date', style: 'weekday' }).text.replace(/^\w+ /, '');
  const paid = `Get paid ${money(quote.bid * 100)} now`;
  if (right === 'P') {
    if (quote.strike >= spot)
      return `${symbol} is already below ${strike}: expect to buy 100 at ${strike}`;
    const fall = formatValue(1 - quote.strike / spot, { kind: 'percent', digits: 0 }).text;
    return `${paid}; buy 100 ${symbol} at ${strike} if it falls ~${fall} by ${by}`;
  }
  if (quote.strike <= spot)
    return `${symbol} is already above ${strike}: expect to sell 100 at ${strike}`;
  const rise = formatValue(quote.strike / spot - 1, { kind: 'percent', digits: 0 }).text;
  return `${paid}; sell 100 ${symbol} at ${strike} if it rises ~${rise} by ${by}`;
}

function n(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** The rows of `right` among one expiry's quotes, strike ascending; `nearMoney` keeps strikes
 * near `spot` (the underlying's price with the chain; null: every strike). */
export function chainRows(
  quotes: readonly OptionQuote[],
  options: {
    right: OptionRight;
    expiry: string;
    symbol: string;
    spot: number | null;
    nearMoney: boolean;
  },
): ChainRow[] {
  const { spot } = options;
  const near = (strike: number) =>
    !options.nearMoney || spot === null || Math.abs(strike / spot - 1) <= NEAR_MONEY;
  return quotes
    .filter((q) => q.right === options.right && q.expiry === options.expiry)
    .flatMap((q): ChainRow[] => {
      const strike = n(q.strike);
      if (strike === null || !near(strike)) return [];
      const bid = n(q.bid);
      return [
        {
          id: q.instrumentId,
          strike,
          bid,
          ask: n(q.ask),
          last: n(q.last),
          volume: n(q.volume),
          openInterest: n(q.openInterest),
          iv: n(q.iv),
          delta: n(q.delta),
          gamma: n(q.gamma),
          theta: n(q.theta),
          vega: n(q.vega),
          inBand: inDeltaBand(q.delta),
          plain: plainEnglish(options.right, { strike, bid }, spot, options.symbol, options.expiry),
        },
      ];
    })
    .sort((a, b) => a.strike - b.strike);
}

/** The expiry to open with: the first at least `minDays` after the session, else the last. */
export function defaultExpiry(chain: OptionChain, minDays = 21): string | null {
  const found = chain.expiries.find((e) => e.days >= minDays);
  return found?.date ?? chain.expiries.at(-1)?.date ?? null;
}

/** The expiries on or after the session (an expired one is not offered). */
export function upcomingExpiries(chain: OptionChain): OptionExpiry[] {
  return chain.expiries.filter((e) => e.days >= 0);
}

/** "20 Nov · 49d": an expiry with the server's calendar days from the session. */
export function expiryLabel(expiry: OptionExpiry): string {
  const date = formatValue(expiry.date, { kind: 'date' }).text.replace(/ \d{4}$/, '');
  return `${date} · ${expiry.days}d`;
}
