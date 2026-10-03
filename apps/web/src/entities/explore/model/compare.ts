/** Compare results shaped for display: rebased price series and side-by-side feature rows. */
import type { ChartSeries } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type PriceComparison = components['schemas']['PriceComparison'];
export type FeatureComparison = components['schemas']['FeatureComparison'];

/** One chart series per instrument (ids are the tickers, so colours follow the compare set). */
export function priceSeries(comparison: PriceComparison): ChartSeries[] {
  return comparison.instruments.map((instrument) => {
    const values = comparison.series[instrument.instrument_id] ?? [];
    const points = comparison.dates.flatMap((time, i) => {
      const value = values[i];
      return typeof value === 'number' ? [{ time, value }] : [];
    });
    const symbol = instrument.symbol ?? instrument.instrument_id;
    return { id: symbol, label: symbol, points };
  });
}

/** Ticker -> value of one feature row. */
export function rowValues(
  comparison: FeatureComparison,
  feature: string,
): Readonly<Record<string, unknown>> {
  const row = comparison.rows.find((r) => r.feature === feature);
  const out: Record<string, unknown> = {};
  for (const instrument of comparison.instruments) {
    out[instrument.symbol ?? instrument.instrument_id] = row?.values[instrument.instrument_id];
  }
  return out;
}
