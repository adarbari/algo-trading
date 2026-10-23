import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ChartEventListPanel } from './ChartEventListPanel';

const hooks = vi.hoisted(() => ({
  useInstrumentEventList: vi.fn(),
}));

vi.mock('@/features/chart-events/api/eventList', () => ({
  useInstrumentEventList: hooks.useInstrumentEventList,
}));
vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));

const SEC = (n: string) =>
  `https://www.sec.gov/Archives/edgar/data/320193/0000320193260000${n}/0000320193-26-0000${n}-index.htm`;
const stored = (kind: string, date: string, values: object, sourceUrl: string | null = null) => ({
  table: `events/${kind}`,
  kind,
  date,
  ts: `${date}T00:00:00+00:00`,
  values,
  sourceUrl,
  confirmed: sourceUrl !== null,
});
const filing = (filingDate: string, label: string, sourceUrl: string | null) => ({
  filingDate,
  form: '8-K',
  label,
  accepted: `${filingDate}T20:05:00Z`,
  knownFrom: filingDate,
  items: [],
  sourceUrl,
});
const study = {
  session: '2026-08-10',
  ahead: [
    {
      date: '2026-08-14',
      time: '08:30',
      kind: 'macro_release',
      label: 'CPI',
      source: 'BLS',
      sourceUrl: 'https://www.bls.gov/cpi/',
    },
    {
      date: '2026-08-12',
      time: 'after_hours',
      kind: 'own_earnings',
      label: 'Earnings',
      source: 'x',
      sourceUrl: null,
    },
  ],
  filings: [
    filing('2026-08-07', 'Results', SEC('70')),
    filing('2026-08-07', 'Other events', SEC('71')),
    filing('2024-08-07', 'Management change', SEC('72')),
  ],
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'));
  hooks.useInstrumentEventList.mockReturnValue(
    fakeQuery({
      events: [
        stored('dividend', '2026-08-10', { cash_amount: 0.27 }),
        stored('earnings', '2026-07-30', { reported: true, time: 'after_hours' }, SEC('69')),
        stored('dividend', '2024-08-10', { cash_amount: 0.25 }),
      ],
      eventStudy: study,
    }),
  );
});

const rows = () =>
  within(screen.getByRole('list', { name: 'AAPL events on the chart' })).getAllByRole('listitem');

describe('ChartEventListPanel', () => {
  it('lists one row per chart marker in the range, newest first', () => {
    render(<ChartEventListPanel symbol="AAPL" from="2025-10-03" />);
    expect(rows().map((r) => r.textContent)).toEqual([
      expect.stringContaining('14 Aug 2026'),
      expect.stringContaining('12 Aug 2026'),
      expect.stringContaining('10 Aug 2026'),
      expect.stringContaining('7 Aug 2026'),
      expect.stringContaining('30 Jul 2026'),
    ]); // 2024's dividend and filing are outside the 1Y range
  });

  it('follows the range: a longer one adds the older rows', () => {
    const { rerender } = render(<ChartEventListPanel symbol="AAPL" from="2026-07-03" />);
    expect(rows()).toHaveLength(5);
    rerender(<ChartEventListPanel symbol="AAPL" from="1990-01-01" />);
    expect(rows()).toHaveLength(7);
  });

  it('links the macro release, each same-day 8-K and the reported earnings; not what has no page', () => {
    render(<ChartEventListPanel symbol="AAPL" from="2025-10-03" />);
    const [macro, ahead, dividend, filings, report] = rows() as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ]; // fmt: skip
    expect(within(macro).getByRole('link')).toHaveAttribute('href', 'https://www.bls.gov/cpi/');
    expect(within(ahead).queryByRole('link')).toBeNull();
    expect(within(dividend).queryByRole('link')).toBeNull();
    expect(
      within(filings)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href')),
    ).toEqual([SEC('70'), SEC('71')]);
    expect(within(report).getByRole('link')).toHaveAttribute('href', SEC('69'));
  });

  it('has a chip per kind with its count that hides the kind', async () => {
    render(<ChartEventListPanel symbol="AAPL" from="2025-10-03" />);
    expect(screen.getByRole('button', { name: 'Filing 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Earnings 2' })).toBeInTheDocument();
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole('button', { name: 'Macro release 1' }));
    expect(rows()).toHaveLength(4);
  });

  it('says so when the ticker has no event in the range', () => {
    hooks.useInstrumentEventList.mockReturnValue(
      fakeQuery({ events: [], eventStudy: { ...study, ahead: [], filings: [] } }),
    );
    render(<ChartEventListPanel symbol="AAPL" from="2025-10-03" />);
    expect(screen.getByText('No events on the AAPL chart in this range.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ChartEventListPanel symbol="AAPL" from="2025-10-03" />);
    vi.useRealTimers();
    await expectNoA11yViolations(container);
  });
});
