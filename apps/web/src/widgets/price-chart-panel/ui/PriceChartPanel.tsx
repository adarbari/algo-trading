/**
 * Chart: the focused ticker's split-adjusted daily closes over the chosen window, with
 * ex-dividend, split and earnings markers, the 8-K filings and the macro release dates of the
 * event study, a volume pane and the sessions the market regime called Storm or Severe storm
 * shaded behind the line.
 */
import { Chart, Panel, type ChartRange } from '@algotrade/ui';
import { useMemo } from 'react';

import { studyChartEvents, useInstrumentEventStudy } from '@/entities/event';
import {
  RangeControl,
  rangeFrom,
  toChartEvents,
  useInstrumentEvents,
  useInstrumentPrices,
} from '@/entities/instrument';
import { toChartBands, useRegimeBands } from '@/entities/regime';

export interface PriceChartPanelProps {
  symbol: string;
  range: ChartRange;
  onRangeChange: (range: ChartRange) => void;
}

export function PriceChartPanel({ symbol, range, onRangeChange }: PriceChartPanelProps) {
  const from = rangeFrom(range);
  const bars = useInstrumentPrices(symbol, from);
  const events = useInstrumentEvents(symbol);
  const study = useInstrumentEventStudy(symbol);
  const items = useMemo(() => bars.data ?? [], [bars.data]);
  // Storm and Severe-storm sessions shade the window, up to the last stored bar.
  const regimeBands = useRegimeBands(from, items.at(-1)?.session);
  const bands = useMemo(() => toChartBands(regimeBands.data ?? [], 'STRESS'), [regimeBands.data]);
  const series = useMemo(
    () => [
      {
        id: symbol,
        label: symbol,
        points: items.map((b) => ({ time: b.session, value: b.close })),
      },
    ],
    [items, symbol],
  );
  const volume = useMemo(() => items.map((b) => ({ time: b.session, value: b.volume })), [items]);
  const markers = useMemo(() => {
    const stored = toChartEvents(events.data ?? []);
    const earnings = new Set(stored.filter((e) => e.kind === 'earnings').map((e) => e.time));
    const studied = study.data ? studyChartEvents(study.data, earnings) : [];
    return [...stored, ...studied]
      .filter((e) => e.time >= from)
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [events.data, study.data, from]);
  return (
    <Panel
      title={`${symbol} · price`}
      description="Split-adjusted closes; dividends, splits, earnings, filings and macro releases marked"
    >
      <Chart
        label={`${symbol} close`}
        series={series}
        events={markers}
        volume={volume}
        bands={bands}
        height="lg"
        toolbar={<RangeControl value={range} onChange={onRangeChange} />}
        status={bars.isError ? 'error' : bars.isPending ? 'loading' : 'ready'}
        errorMessage={`${symbol} bars failed to load.`}
        onRetry={() => void bars.refetch()}
        emptyMessage={`No stored bars for ${symbol} in this window.`}
      />
    </Panel>
  );
}
