import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, expiryFridays, manyNames, names, sampleDays } from '../../testing';
import { cellsOf, namesOf, pageOf } from './calendarModel';
import { CalendarGrid } from './CalendarGrid';

describe('CalendarGrid model', () => {
  it('takes the names given, else the distinct names in the events in first-seen order', () => {
    expect(namesOf(sampleDays, names)).toEqual(names);
    expect(namesOf(sampleDays, undefined).map((n) => n.symbol)).toEqual([
      'TSLA',
      'NVDA',
      'AAPL',
      'MSFT',
    ]);
  });

  it('keys events by day and name', () => {
    const cells = cellsOf(sampleDays);
    expect(cells.get('2026-10-28|EQ:NVDA')?.map((e) => e.label)).toEqual(['FOMC', 'MSFT earnings']);
    expect(cells.get('2026-10-28|EQ:TSLA')?.map((e) => e.label)).toEqual(['FOMC']);
  });

  it('pages names and clamps the page', () => {
    const list = Array.from({ length: 64 }, (_, i) => i);
    expect(pageOf(list, 0, 30)).toMatchObject({ pages: 3, from: 1, to: 30 });
    expect(pageOf(list, 2, 30)).toMatchObject({ page: 2, from: 61, to: 64 });
    expect(pageOf(list, 9, 30).page).toBe(2);
    expect(pageOf([], 0, 30)).toMatchObject({ pages: 1, from: 0, to: 0 });
  });
});

describe('CalendarGrid', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('puts days down the rows and names across the columns, chips in the cells', () => {
    render(
      <CalendarGrid label="Events" days={sampleDays} names={names} ruledDays={expiryFridays} />,
    );
    const table = screen.getByRole('table', { name: 'Events' });
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((h) => h.textContent),
    ).toEqual(['NVDA', 'AAPL', 'TSLA', 'MSFT']);
    const row = screen.getByRole('row', { name: /Wed 14 Oct/ });
    expect(within(row).getAllByText('CPI')).toHaveLength(4);
  });

  it('rules the expiry days and names the rule in the day header', () => {
    render(
      <CalendarGrid label="Events" days={sampleDays} names={names} ruledDays={expiryFridays} />,
    );
    const header = screen.getByRole('rowheader', { name: /Fri 16 Oct/ });
    expect(header).toHaveTextContent('Expiry');
    expect(header).toHaveAttribute('data-ruled');
    expect(screen.getByRole('rowheader', { name: /Wed 14 Oct/ })).not.toHaveAttribute('data-ruled');
  });

  it('flips to days across when forced, with names as the rows', () => {
    render(
      <CalendarGrid label="Events" days={sampleDays} names={names} orientation="days-across" />,
    );
    expect(screen.getAllByRole('rowheader').map((h) => h.textContent)).toEqual([
      'NVDA',
      'AAPL',
      'TSLA',
      'MSFT',
    ]);
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('Fri 9 Oct');
  });

  it('flips to days across under the medium breakpoint when measured', () => {
    // Floating UI (the chips' tooltips) observes too: tell every observer the grid's width.
    const callbacks: ResizeObserverCallback[] = [];
    const notify = (entries: ResizeObserverEntry[], observer: ResizeObserver) => {
      callbacks.forEach((callback) => {
        callback(entries, observer);
      });
    };
    class FakeObserver {
      constructor(callback: ResizeObserverCallback) {
        callbacks.push(callback);
      }
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal('ResizeObserver', FakeObserver);
    render(<CalendarGrid label="Events" days={sampleDays} names={names} />);
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('NVDA');
    act(() => {
      notify([{ contentRect: { width: 375 } } as ResizeObserverEntry], {} as ResizeObserver);
    });
    expect(screen.getAllByRole('rowheader')[0]).toHaveTextContent('NVDA');
    act(() => {
      notify([{ contentRect: { width: 1200 } } as ResizeObserverEntry], {} as ResizeObserver);
    });
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('NVDA');
  });

  it('pages the names beyond the page size', async () => {
    const many = manyNames(64);
    render(<CalendarGrid label="Events" days={many.days} names={many.names} />);
    expect(screen.getByText('Names 1-30 of 64')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(30);
    expect(screen.getByRole('button', { name: 'Previous names' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Next names' }));
    expect(screen.getByText('Names 31-60 of 64')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'SYM31' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next names' }));
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    expect(screen.getByRole('button', { name: 'Next names' })).toBeDisabled();
  });

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<CalendarGrid label="Events" days={[]} status="loading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading Events');
    rerender(<CalendarGrid label="Events" days={[]} />);
    expect(screen.getByText('No events in this window.')).toBeInTheDocument();
    rerender(<CalendarGrid label="Events" days={[]} status="error" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <CalendarGrid label="Events" days={sampleDays} names={names} ruledDays={expiryFridays} />
        <CalendarGrid
          label="Events, flipped"
          days={sampleDays}
          names={names}
          orientation="days-across"
        />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
