import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { cpi, earnings, expectNoA11yViolations } from '../../testing';
import { ExpiryLadder, type ExpiryRow } from './ExpiryLadder';

const rows: ExpiryRow[] = [
  { expiry: '2026-10-09', dte: 7, events: [], clear: true, firstClear: true },
  { expiry: '2026-10-16', dte: 14, events: [cpi], clear: false, firstClear: false },
  { expiry: '2026-10-23', dte: 21, events: [cpi, earnings], clear: false, firstClear: false },
];

describe('ExpiryLadder', () => {
  it('is a table named by its label with one row per expiry', () => {
    render(<ExpiryLadder label="NVDA expiries" rows={rows} />);
    const table = screen.getByRole('table', { name: 'NVDA expiries' });
    expect(within(table).getAllByRole('row')).toHaveLength(4);
    expect(screen.getByRole('rowheader', { name: 'Fri 9 Oct' })).toBeInTheDocument();
  });

  it('shows the events each expiry spans with their days, and Clear when none', () => {
    render(<ExpiryLadder label="NVDA expiries" rows={rows} />);
    const [, clear, one, two] = screen.getAllByRole('row') as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ];
    expect(within(clear).getByText('Clear')).toBeInTheDocument();
    expect(within(one).getByText('CPI')).toBeInTheDocument();
    expect(within(one).getByText('14 Oct')).toBeInTheDocument();
    expect(within(two).getByText('Earnings')).toBeInTheDocument();
    expect(within(two).getByText('22 Oct')).toBeInTheDocument();
  });

  it('marks the first clear row in words, once', () => {
    render(<ExpiryLadder label="NVDA expiries" rows={rows} />);
    expect(screen.getAllByText('First clear')).toHaveLength(1);
    expect(
      within(screen.getAllByRole('row')[1] as HTMLElement).getByText('First clear'),
    ).toBeInTheDocument();
  });

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ExpiryLadder label="NVDA expiries" rows={[]} status="loading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading NVDA expiries');
    rerender(<ExpiryLadder label="NVDA expiries" rows={[]} />);
    expect(screen.getByText('No listed expiries in this range.')).toBeInTheDocument();
    rerender(<ExpiryLadder label="NVDA expiries" rows={[]} status="error" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ExpiryLadder label="NVDA expiries" rows={rows} />);
    await expectNoA11yViolations(container);
  });
});
