import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  cpi,
  earnings,
  expectNoA11yViolations,
  fomc,
  oneOfEach,
  referenceEarnings,
} from '../../testing';
import { fraction, groupByDay, monthStarts } from './axis';
import { EventTimeline } from './EventTimeline';

const window = { start: '2026-10-02', end: '2026-12-31' };

describe('EventTimeline axis', () => {
  it('places a day as a fraction of the window and clamps outside it', () => {
    expect(fraction('2026-10-02', '2026-10-02', '2026-10-12')).toBe(0);
    expect(fraction('2026-10-07', '2026-10-02', '2026-10-12')).toBe(0.5);
    expect(fraction('2027-01-01', '2026-10-02', '2026-10-12')).toBe(1);
    expect(fraction('2026-10-02', '2026-10-02', '2026-10-02')).toBe(0);
  });

  it('lists the month starts after the first day of the window', () => {
    expect(monthStarts('2026-10-02', '2026-12-31')).toEqual(['2026-11-01', '2026-12-01']);
    expect(monthStarts('2026-10-01', '2026-10-31')).toEqual([]);
  });

  it('groups by day, oldest first, dropping events outside the window', () => {
    const days = groupByDay(
      [fomc, referenceEarnings, cpi, { ...cpi, date: '2027-02-01' }],
      window.start,
      window.end,
    );
    expect(days.map((d) => d.date)).toEqual(['2026-10-14', '2026-10-28']);
    expect(days[1]?.events.map((e) => e.label)).toEqual(['FOMC', 'NVDA earnings']);
  });
});

describe('EventTimeline', () => {
  it('lists the days with their chips, one list item per day', () => {
    render(<EventTimeline label="NVDA events" events={[...oneOfEach, fomc]} {...window} />);
    const list = screen.getByRole('list', { name: 'NVDA events' });
    const items = within(list).getAllByRole('listitem');
    // 14, 16, 22 and 28 Oct (the July filing is outside the window); the 28th holds two events.
    expect(items).toHaveLength(4);
    expect(within(items[3] as HTMLElement).getByText('FOMC')).toBeInTheDocument();
    expect(within(items[3] as HTMLElement).getByText('NVDA earnings')).toBeInTheDocument();
  });

  it('shows the details of an event on focus', async () => {
    render(<EventTimeline label="Events" events={[earnings]} {...window} />);
    await userEvent.tab();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Source: Company calendar');
  });

  it('collapses a day to a count whose tooltip lists the events when dense', async () => {
    render(<EventTimeline label="Events" events={[referenceEarnings, fomc]} dense {...window} />);
    expect(screen.queryByRole('tooltip')).toBeNull();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Wed 28 Oct: 2 events' })).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toHaveTextContent('NVDA earnings');
  });

  it('shows a loading, an empty and an error state', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <EventTimeline label="Events" events={[]} {...window} status="loading" />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Loading Events');
    rerender(<EventTimeline label="Events" events={[]} {...window} />);
    expect(screen.getByText('No events in this window.')).toBeInTheDocument();
    rerender(
      <EventTimeline label="Events" events={[]} {...window} status="error" onRetry={onRetry} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <EventTimeline label="Events" events={oneOfEach} {...window} />
        <EventTimeline label="Dense events" events={oneOfEach} {...window} dense />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
