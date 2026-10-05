/**
 * Compare: the compare set's performance rebased to 100 over the chosen window, one series
 * colour per ticker (as in the compare bar), from one request for the whole set. The tickers'
 * features side by side are the feature table beside it (the page composes both).
 */
import { Chart, EmptyState, Panel, type ChartRange } from '@algotrade/ui';
import { useMemo } from 'react';

import { seriesOf } from '@/features/compare-set';
import { priceSeries, REBASE, useComparePrices } from '@/entities/explore';
import { RangeControl, rangeFrom } from '@/entities/instrument';

export interface ComparePanelProps {
  /** The compare set, in pick order (series colours follow it). */
  symbols: readonly string[];
  range: ChartRange;
  onRangeChange: (range: ChartRange) => void;
}

export function ComparePanel({ symbols, range, onRangeChange }: ComparePanelProps) {
  const prices = useComparePrices(symbols, rangeFrom(range));
  const series = useMemo(
    () =>
      priceSeries(prices.data ?? []).map((s) => {
        const tone = seriesOf(symbols, s.id);
        return tone ? { ...s, tone } : s;
      }),
    [prices.data, symbols],
  );
  if (symbols.length === 0) {
    return (
      <EmptyState
        bordered
        icon="search"
        title="Nothing to compare yet"
        description="Tick tickers in the table (up to six) to compare their performance and features."
      />
    );
  }
  return (
    <Panel title={`Performance · rebased to ${REBASE} · ${range}`}>
      <Chart
        label={`${symbols.join(', ')} rebased to ${REBASE}`}
        series={series}
        format={{ kind: 'number', digits: 1 }}
        height="lg"
        toolbar={<RangeControl value={range} onChange={onRangeChange} />}
        status={prices.isError ? 'error' : prices.isPending ? 'loading' : 'ready'}
        errorMessage="Prices failed to load."
        onRetry={() => void prices.refetch()}
        emptyMessage="No stored prices in this window."
      />
    </Panel>
  );
}
