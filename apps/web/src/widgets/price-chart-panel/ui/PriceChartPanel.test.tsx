import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChartProps } from '@algotrade/ui';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { PriceChartPanel } from './PriceChartPanel';

const hooks = vi.hoisted(() => ({
  useInstrumentBars: vi.fn(),
  useInstrumentEvents: vi.fn(),
  chart: vi.fn(),
}));

vi.mock('@algotrade/ui', async (importOriginal) => {
  const ui = await importOriginal<Record<string, unknown>>();
  const { Text } = await import('@algotrade/ui');
  return {
    ...ui,
    // jsdom has no canvas: the chart is checked by the props it receives.
    Chart: (props: ChartProps) => {
      hooks.chart(props);
      return (
        <>
          <Text>{props.label}</Text>
          {props.toolbar}
        </>
      );
    },
  };
});
vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentBars: hooks.useInstrumentBars,
  useInstrumentEvents: hooks.useInstrumentEvents,
}));

const bar = (session_date: string, close: number) => ({
  ts: `${session_date}T20:00:00+00:00`,
  session_date,
  open: close,
  high: close,
  low: close,
  close,
  volume: 1000,
  vwap: null,
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'));
  hooks.chart.mockClear();
  hooks.useInstrumentBars.mockReturnValue(
    fakeQuery({ items: [bar('2026-08-07', 220), bar('2026-08-10', 229)] }),
  );
  hooks.useInstrumentEvents.mockReturnValue(
    fakeQuery([
      { table: 'events/dividend', ts: '2026-08-10T00:00:00+00:00', values: { cash_amount: 0.27 } },
      { table: 'events/dividend', ts: '2024-08-10T00:00:00+00:00', values: { cash_amount: 0.25 } },
    ]),
  );
});

describe('PriceChartPanel', () => {
  it('charts closes and volume with the events inside the window', async () => {
    const onRangeChange = vi.fn();
    const { container } = render(
      <PriceChartPanel symbol="AAPL" range="1Y" onRangeChange={onRangeChange} />,
    );
    expect(hooks.useInstrumentBars).toHaveBeenCalledWith('AAPL', '2025-10-03');
    const chart = hooks.chart.mock.lastCall?.[0] as ChartProps;
    expect(chart.series[0]?.points).toEqual([
      { time: '2026-08-07', value: 220 },
      { time: '2026-08-10', value: 229 },
    ]);
    expect(chart.volume).toHaveLength(2);
    expect(chart.events).toEqual([{ time: '2026-08-10', kind: 'dividend', detail: '$0.27' }]);
    vi.useRealTimers();
    await expectNoA11yViolations(container);
    await userEvent.setup().click(screen.getByRole('radio', { name: '3M' }));
    expect(onRangeChange).toHaveBeenCalledWith('3M');
  });
});
