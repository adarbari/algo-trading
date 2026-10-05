/**
 * The compare chart's series: each ticker's stored closes, shown rebased to 100 at its first
 * close in the window so tickers at different prices share one axis. Rebasing is how the chart
 * presents the closes the server sent (ADR 0038 "presentation is not derivation"); no value is
 * computed that the server could send.
 */
import type { ChartSeries } from '@algotrade/ui';

export const REBASE = 100;

/** One ticker's closes, oldest first. */
export interface ComparedPrices {
  symbol: string;
  instrumentId: string;
  closes: readonly { session: string; close: number | null }[];
}

interface ServedInstrument {
  instrumentId: string;
  symbol: string;
  prices: { bars: readonly { session: string; close?: number | null }[] };
}

export function toCompared(instruments: readonly ServedInstrument[]): ComparedPrices[] {
  return instruments.map((i) => ({
    symbol: i.symbol,
    instrumentId: i.instrumentId,
    closes: i.prices.bars.map((b) => ({ session: b.session, close: b.close ?? null })),
  }));
}

/** One chart series per ticker (ids are the tickers, so colours follow the compare set). */
export function priceSeries(compared: readonly ComparedPrices[]): ChartSeries[] {
  return compared.map(({ symbol, closes }) => {
    const known = closes.filter((c): c is { session: string; close: number } => c.close !== null);
    const first = known[0]?.close;
    const points =
      first === undefined || first === 0
        ? []
        : known.map((c) => ({ time: c.session, value: (c.close / first) * REBASE }));
    return { id: symbol, label: symbol, points };
  });
}
