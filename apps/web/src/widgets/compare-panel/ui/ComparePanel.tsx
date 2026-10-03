/**
 * Compare: the compare set's performance rebased to 100 over the chosen window (one series
 * colour per ticker, as in the compare bar), and the tickers side by side on chosen
 * dimensions (catalogue features).
 */
import { Chart, EmptyState, Panel, Stack, type ChartRange } from '@algotrade/ui';
import { useMemo } from 'react';

import { seriesOf } from '@/features/compare-set';
import { priceSeries, useComparePrices } from '@/entities/explore';
import { RangeControl, rangeFrom } from '@/entities/instrument';

import { SideBySide } from './SideBySide';

export interface ComparePanelProps {
  /** The compare set, in pick order (series colours follow it). */
  symbols: readonly string[];
  range: ChartRange;
  onRangeChange: (range: ChartRange) => void;
  dimensions: readonly string[];
  onDimensionsChange: (dimensions: string[]) => void;
}

export function ComparePanel({
  symbols,
  range,
  onRangeChange,
  dimensions,
  onDimensionsChange,
}: ComparePanelProps) {
  const prices = useComparePrices(symbols, rangeFrom(range));
  const series = useMemo(
    () =>
      (prices.data ? priceSeries(prices.data) : []).map((s) => {
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
    <Stack gap={4}>
      <Panel title={`Performance · rebased to 100 · ${range}`}>
        <Chart
          label={`${symbols.join(', ')} rebased to 100`}
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
      <SideBySide
        symbols={symbols}
        dimensions={dimensions}
        onDimensionsChange={onDimensionsChange}
      />
    </Stack>
  );
}
