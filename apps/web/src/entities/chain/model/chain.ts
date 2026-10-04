/**
 * One underlying's option chain shaped for the Options view: the rows of one expiry and right
 * (puts or calls), the 8-15 delta band short-premium sellers look at, and a plain-English line
 * per contract ("Get paid $820 now; buy 100 AAPL at $325 if it falls ~2.6% by 20 Nov").
 */
import { formatValue } from '@algotrade/ui';

import type { components } from '@/shared/api';
import { daysBetween } from '@/shared/lib';

export type OptionChain = components['schemas']['OptionChain'];
export type OptionQuote = components['schemas']['OptionQuote'];
export type OptionRight = 'P' | 'C';

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

/** The underlying's price with the chain (its close when no last price was captured). */
export function spotOf(chain: OptionChain): number | null {
  const price = chain.underlying?.['price'] ?? chain.underlying?.['close'];
  return typeof price === 'number' && Number.isFinite(price) ? price : null;
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

const n = (value: number | null | undefined): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/** The rows of `expiry` for `right`, strike ascending; `nearMoney` keeps strikes near the spot. */
export function chainRows(
  chain: OptionChain,
  options: { right: OptionRight; expiry: string; symbol: string; nearMoney: boolean },
): ChainRow[] {
  const spot = spotOf(chain);
  const near = (strike: number) =>
    !options.nearMoney || spot === null || Math.abs(strike / spot - 1) <= NEAR_MONEY;
  return chain.quotes
    .filter((q) => q.right === options.right && q.expiry === options.expiry)
    .flatMap((q): ChainRow[] => {
      const strike = n(q.strike);
      if (strike === null || !near(strike)) return [];
      const bid = n(q.bid);
      return [
        {
          id: q.instrument_id,
          strike,
          bid,
          ask: n(q.ask),
          last: n(q.last),
          volume: n(q.volume),
          openInterest: n(q.open_interest),
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
  const found = chain.expiries.find((e) => daysBetween(chain.session, e) >= minDays);
  return found ?? chain.expiries.at(-1) ?? null;
}

/** "20 Nov · 49d": an expiry with its calendar days from the session. */
export function expiryLabel(session: string, expiry: string): string {
  const date = formatValue(expiry, { kind: 'date' }).text.replace(/ \d{4}$/, '');
  return `${date} · ${daysBetween(session, expiry)}d`;
}
