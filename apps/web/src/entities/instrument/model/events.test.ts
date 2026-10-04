import { describe, expect, it } from 'vitest';

import { displayName, fieldValue, historyOf, type InstrumentDetail } from './detail';
import { splitRatio, toChartEvents, toTimeline, type InstrumentEvent } from './events';
import { rangeFrom } from './range';

const events: InstrumentEvent[] = [
  {
    table: 'events/dividend',
    ts: '2026-08-10T00:00:00+00:00',
    values: { cash_amount: 0.27, pay_date: '2026-08-13', distribution_type: 'recurring' },
  },
  {
    table: 'events/earnings',
    ts: '2026-10-29T00:00:00+00:00',
    values: { fiscal_quarter: 'Sep/2026', time: 'post', eps_forecast: 1.98, reported: false },
  },
  {
    table: 'events/split',
    ts: '2024-06-10T00:00:00+00:00',
    values: { split_from: 1, split_to: 10, adjustment_type: 'forward_split' },
  },
  {
    table: 'events/reference_change',
    ts: '2026-10-02T00:00:00+00:00',
    values: { change: 'id_changed', old: 'EQ:NVDA', new: 'EQ:BBG000BBJQV0' },
  },
];

describe('instrument events', () => {
  it('builds a newest-first timeline with plain details', () => {
    expect(toTimeline(events).map((e) => [e.date, e.label, e.detail])).toEqual([
      [
        '2026-10-29',
        'Earnings',
        'Quarter Sep/2026 · after the close · EPS forecast $1.98 · not reported yet',
      ],
      ['2026-10-02', 'Reference change', 'Instrument id EQ:NVDA → EQ:BBG000BBJQV0'],
      ['2026-08-10', 'Ex-dividend', '$0.27 cash · paid 13 Aug 2026'],
      ['2024-06-10', 'Split', '10-for-1'],
    ]);
  });

  it('reads split ratios, reverse splits included', () => {
    expect(splitRatio({ split_from: 80, split_to: 1 })).toBe('1-for-80');
    expect(splitRatio({ split_from: 2, split_to: 3 })).toBe('3-for-2');
    expect(splitRatio({})).toBe('');
  });

  it('marks dividends, splits and earnings on the chart, oldest first', () => {
    expect(toChartEvents(events)).toEqual([
      { time: '2024-06-10', kind: 'split', detail: '10-for-1' },
      { time: '2026-08-10', kind: 'dividend', detail: '$0.27' },
      { time: '2026-10-29', kind: 'earnings' },
    ]);
  });
});

describe('instrument detail', () => {
  const detail: InstrumentDetail = {
    instrument_id: 'EQ:A',
    reference_snapshot: '2026-10-02',
    reference: { symbol: 'AAPL', name: 'Apple Inc. - Common Stock', optionable: true },
    company: { name: 'Apple Inc.', sector: 'Technology' },
    features: { 'feature.market_cap': 4.87e12 },
    feature_sessions: {},
  };

  it('reads catalogue fields from reference, company and features', () => {
    expect(fieldValue(detail, 'instrument.optionable')).toBe(true);
    expect(fieldValue(detail, 'instrument.sector')).toBe('Technology');
    expect(fieldValue(detail, 'feature.market_cap')).toBe(4.87e12);
    expect(fieldValue(detail, 'feature.unknown')).toBeUndefined();
    expect(displayName(detail)).toBe('Apple Inc.');
    expect(displayName({ ...detail, company: null })).toBe('Apple Inc. - Common Stock');
  });

  it('reads one feature history with gaps', () => {
    const series = {
      instrument_id: 'EQ:A',
      names: ['x'],
      start: '2026-09-01',
      end: '2026-09-03',
      items: [{ x: 1 }, { x: null }, { x: 'n/a' }, { x: 2.5 }],
    };
    expect(historyOf(series, 'x')).toEqual([1, null, null, 2.5]);
  });

  it('counts chart windows back from today', () => {
    expect(rangeFrom('3M', '2026-10-02')).toBe('2026-07-02');
    expect(rangeFrom('2Y', '2026-10-02')).toBe('2024-10-02');
    expect(rangeFrom('All', '2026-10-02')).toBe('1990-01-01');
  });
});
