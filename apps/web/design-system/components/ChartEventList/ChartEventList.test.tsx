import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import type { ChartEvent } from '../Chart';
import { ChartEventList } from './ChartEventList';

const SEC =
  'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/0000000001-26-000001-index.htm';
const rows: ChartEvent[] = [
  {
    time: '2026-10-14',
    kind: 'macro',
    parts: [{ text: 'CPI 08:30 ET', href: 'https://www.bls.gov/cpi/' }],
  },
  {
    time: '2026-08-14',
    kind: 'filing',
    parts: [
      { text: '8-K Results', href: SEC },
      { text: '8-K Other events', href: `${SEC}#2` },
    ],
  },
  { time: '2026-07-30', kind: 'earnings', parts: [{ text: 'Reported before the open' }] },
  { time: '2026-05-11', kind: 'dividend', parts: [{ text: '$0.26' }] },
]; // fmt: skip

const rowsOf = () =>
  within(screen.getByRole('list', { name: 'AAPL events' })).getAllByRole('listitem');

describe('ChartEventList', () => {
  it('lists one row per event in the order given, with date, kind letter and description', () => {
    render(<ChartEventList label="AAPL events" events={rows} />);
    const items = rowsOf();
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent('14 Oct 2026');
    expect(items[0]).toHaveTextContent('M');
    expect(within(items[0] as HTMLElement).getByText('Macro release')).toBeInTheDocument();
    expect(items[2]).toHaveTextContent('E');
    expect(items[3]).toHaveTextContent('D');
  });

  it('renders a part with an address as an external link and one without as plain text', () => {
    render(<ChartEventList label="AAPL events" events={rows} />);
    const cpi = screen.getByRole('link', { name: 'CPI 08:30 ET, opens in a new tab' });
    expect(cpi).toHaveAttribute('href', 'https://www.bls.gov/cpi/');
    expect(cpi).toHaveAttribute('target', '_blank');
    expect(screen.queryByRole('link', { name: /Reported before the open/ })).toBeNull();
    expect(screen.getByText('Reported before the open')).toBeInTheDocument();
  });

  it('keeps the filings of one day as separate links inside one row', () => {
    render(<ChartEventList label="AAPL events" events={rows} />);
    const row = rowsOf()[1] as HTMLElement;
    const links = within(row).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual([SEC, `${SEC}#2`]);
  });

  it('has a chip per kind present with its count, and toggling one hides its rows', async () => {
    const user = userEvent.setup();
    render(<ChartEventList label="AAPL events" events={rows} />);
    expect(screen.getByRole('button', { name: 'Filing 1', pressed: true })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Split/ })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Filing 1' }));
    expect(rowsOf()).toHaveLength(3);
    expect(screen.getByRole('button', { name: 'Filing 1', pressed: false })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Filing 1' }));
    expect(rowsOf()).toHaveLength(4);
  });

  it('says so when every kind is switched off', async () => {
    const user = userEvent.setup();
    render(<ChartEventList label="AAPL events" events={[rows[2] as ChartEvent]} />);
    await user.click(screen.getByRole('button', { name: 'Earnings 1' }));
    expect(screen.getByText('No kind is selected.')).toBeInTheDocument();
  });

  it('falls back to the detail after the kind name, then to the kind name', () => {
    const bare: ChartEvent[] = [
      { time: '2026-10-14', kind: 'dividend', detail: '$0.26' },
      { time: '2026-10-01', kind: 'earnings' },
    ];
    render(<ChartEventList label="AAPL events" events={bare} />);
    expect(screen.getByText('Ex-dividend $0.26')).toBeInTheDocument();
    expect(within(rowsOf()[1] as HTMLElement).getAllByText('Earnings')).toHaveLength(2); // letter name, words
  });

  it('shows the empty, loading and error states', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ChartEventList label="AAPL events" events={[]} />);
    expect(screen.getByText('No events on the chart in this range.')).toBeInTheDocument();
    rerender(<ChartEventList label="AAPL events" events={rows} status="loading" />);
    expect(screen.getByText('Loading AAPL events')).toBeInTheDocument();
    rerender(
      <ChartEventList
        label="AAPL events"
        events={rows}
        status="error"
        onRetry={onRetry}
        errorMessage="Failed."
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ChartEventList label="AAPL events" events={rows} />);
    await expectNoA11yViolations(container);
  });
});
