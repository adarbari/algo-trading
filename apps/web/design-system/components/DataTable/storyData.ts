/**
 * Deterministic sample rows for the DataTable stories and tests: the screener preview from
 * the approved mockups, and a seeded universe of 11,427 tickers for the virtual-scrolling
 * story (same rows on every run, so screenshots are stable). Not exported from @algotrade/ui.
 */

export interface ScreenRow {
  symbol: string;
  decision: 'QUALIFIED' | 'WATCH' | 'EVENT_RISK';
  score: number;
  iv30: number;
  hv30: number;
  spread: number;
  ratio: number;
  fromHigh: number;
  adv: number;
  earnings: number | null;
  flags: string;
}

export const screenRows: ScreenRow[] = [
  ['[SYM 1]', 'QUALIFIED', 84, 0.721, 0.483, 23.8, 1.49, -0.031, 412e6, 31, 'ADR'],
  ['[SYM 2]', 'QUALIFIED', 79, 0.584, 0.41, 17.4, 1.42, -0.068, 1.2e9, 22, ''],
  ['[SYM 3]', 'QUALIFIED', 71, 0.64, 0.497, 14.3, 1.29, -0.092, 96e6, 40, 'leveraged 2×'],
  ['[SYM 4]', 'WATCH', 66, 0.552, 0.426, 12.6, 1.3, -0.044, 38e6, 18, 'ADV below $50M'],
  ['[SYM 5]', 'EVENT_RISK', 63, 0.815, 0.52, 29.5, 1.57, 0, 2.4e9, 6, 'earnings < 14 days'],
  ['[SYM 6]', 'WATCH', 58, 0.519, 0.402, 11.7, 1.29, -0.087, 61e6, null, 'single-expiry IV'],
].map(([symbol, decision, score, iv30, hv30, spread, ratio, fromHigh, adv, earnings, flags]) => ({
  symbol: symbol as string,
  decision: decision as ScreenRow['decision'],
  score: score as number,
  iv30: iv30 as number,
  hv30: hv30 as number,
  spread: spread as number,
  ratio: ratio as number,
  fromHigh: fromHigh as number,
  adv: adv as number,
  earnings: earnings as number | null,
  flags: flags as string,
}));

export interface TickerRow {
  id: string;
  symbol: string;
  name: string;
  close: number;
  iv30: number | null;
  ivHv: number | null;
  fromHigh: number;
  earnings: number | null;
  adv: number;
  marketCap: number;
  listed: string;
}

/** Mulberry32: a tiny seeded PRNG, so the universe is identical on every run. */
function random(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const NAMES = [
  'Holdings',
  'Group',
  'Therapeutics',
  'Energy',
  'Capital',
  'Systems',
  'Bancorp',
  'Labs',
  'Trust',
  'ETF',
];
const FIRST: TickerRow[] = [
  ['AAPL', 'Apple', 333.69, 0.244, 1.15, -0.034, 19],
  ['MSFT', 'Microsoft', 512.4, 0.221, 1.08, -0.052, 24],
  ['NVDA', 'NVIDIA', 187.2, 0.412, 1.21, -0.071, 47],
  ['SPY', 'S&P 500 ETF', 769.64, 0.129, 1.25, -0.012, null],
  ['QQQ', 'Nasdaq-100 ETF', 621.1, 0.19, 1.19, -0.018, null],
].map(([symbol, name, close, iv30, ivHv, fromHigh, earnings], i) => ({
  id: symbol as string,
  symbol: symbol as string,
  name: name as string,
  close: close as number,
  iv30: iv30 as number,
  ivHv: ivHv as number,
  fromHigh: fromHigh as number,
  earnings: earnings as number | null,
  adv: [13.99e9, 9.1e9, 30.2e9, 41.5e9, 18.7e9][i] as number,
  marketCap: [4.87e12, 3.9e12, 4.4e12, 0, 0][i] as number,
  listed: ['1980-12-12', '1986-03-13', '1999-01-22', '1993-01-22', '1999-03-10'][i] as string,
}));

/** `count` tickers (default 11,427, the size of the covered universe), seeded. */
export function makeUniverse(count = 11_427, seed = 7): TickerRow[] {
  const next = random(seed);
  const rows = FIRST.slice(0, Math.min(count, FIRST.length));
  const seen = new Set(rows.map((r) => r.symbol));
  while (rows.length < count) {
    const length = 2 + Math.floor(next() * 3);
    let symbol = '';
    for (let i = 0; i < length; i += 1) symbol += LETTERS.charAt(Math.floor(next() * 26));
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    const optionable = next() > 0.3;
    const year = 1970 + Math.floor(next() * 55);
    rows.push({
      id: symbol,
      symbol,
      name: `${symbol.charAt(0)}${symbol.slice(1).toLowerCase()} ${NAMES[Math.floor(next() * NAMES.length)]}`,
      close: Math.round(next() ** 2 * 80_000) / 100 + 1,
      iv30: optionable ? Math.round((0.1 + next() * 0.9) * 1000) / 1000 : null,
      ivHv: optionable ? Math.round((0.7 + next() * 1.0) * 100) / 100 : null,
      fromHigh: -Math.round(next() ** 2 * 600) / 1000,
      earnings: next() > 0.2 ? Math.floor(next() * 63) : null,
      adv: Math.round(10 ** (5 + next() * 5.5)),
      marketCap: Math.round(10 ** (7 + next() * 5.5)),
      listed: `${year}-${String(1 + Math.floor(next() * 12)).padStart(2, '0')}-${String(1 + Math.floor(next() * 28)).padStart(2, '0')}`,
    });
  }
  return rows;
}
