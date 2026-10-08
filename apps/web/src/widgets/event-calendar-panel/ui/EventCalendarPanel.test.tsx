import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CALENDAR_FIXTURE as CALENDAR } from '@/entities/event';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EventCalendarPanel } from './EventCalendarPanel';

const hooks = vi.hoisted(() => ({
  useEventCalendar: vi.fn(),
  useScreeners: vi.fn(),
  useScreenerResults: vi.fn(),
}));

vi.mock('@/entities/event', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEventCalendar: hooks.useEventCalendar,
}));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreeners: hooks.useScreeners,
  useScreenerResults: hooks.useScreenerResults,
}));

stubElementSize();

const picks = (ids: string[]) =>
  fakeQuery({
    screener: {
      latestRun: { results: { results: ids.map((instrumentId) => ({ instrumentId })) } },
    },
  });

beforeEach(() => {
  hooks.useEventCalendar.mockReturnValue(fakeQuery(CALENDAR));
  hooks.useScreeners.mockReturnValue(fakeQuery([{ configId: 'vrp_scanner' }]));
  hooks.useScreenerResults.mockReturnValue(picks(['EQ:A']));
});

describe('EventCalendarPanel', () => {
  it('shows the scope list by default: names, a Market column and the ruled expiry day', async () => {
    const { container } = render(<EventCalendarPanel />);
    expect(hooks.useEventCalendar).toHaveBeenLastCalledWith([], true, true);
    const grid = screen.getByRole('table', { name: 'Events, next 90 days: scope list' });
    for (const symbol of ['Market', 'AAPL', 'NVDA']) {
      expect(within(grid).getByRole('columnheader', { name: symbol })).toBeInTheDocument();
    }
    expect(within(grid).getByText('Expiry')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("asks for the names of a chosen screener's latest results", async () => {
    render(<EventCalendarPanel />);
    await userEvent.setup().selectOptions(screen.getByLabelText('Names'), 'vrp_scanner');
    expect(hooks.useEventCalendar).toHaveBeenLastCalledWith(['EQ:A'], false, true);
    expect(
      screen.getByRole('table', { name: 'Events, next 90 days: vrp_scanner' }),
    ).toBeInTheDocument();
  });

  it('says why a screener without a run has no calendar, and asks for nothing', async () => {
    hooks.useScreenerResults.mockReturnValue(
      fakeQuery({
        screener: {
          latestRun: null,
          notRun: {
            code: 'NOT_RUN',
            kind: 'NOT_RUN',
            guideTerm: 'not_run',
            kindText: 'not run for this session',
            cause: null,
          },
        },
      }),
    );
    hooks.useEventCalendar.mockReturnValue(fakeQuery(undefined, { isPending: true }));
    render(<EventCalendarPanel />);
    await userEvent.setup().selectOptions(screen.getByLabelText('Names'), 'vrp_scanner');
    expect(screen.getByText('This screener: not run for this session.')).toBeInTheDocument();
    expect(hooks.useEventCalendar).toHaveBeenLastCalledWith([], false, false);
  });

  it('renders the gaps and the names the snapshot lacks', () => {
    hooks.useEventCalendar.mockReturnValue(
      fakeQuery({
        ...CALENDAR,
        gaps: [
          {
            instrumentId: null,
            part: 'macro_release',
            unknown: {
              code: 'NO_PARTITION',
              kind: 'SYSTEM',
              guideTerm: 'unavailable_system',
              kindText: 'not available because of a system error',
              cause: null,
              reason: null,
            },
          },
        ],
        unresolved: ['XYZ'],
      }),
    );
    render(<EventCalendarPanel />);
    expect(
      screen.getByText('Macro releases: not available because of a system error'),
    ).toBeInTheDocument();
    expect(screen.getByText('XYZ')).toBeInTheDocument();
  });

  it('shows an error panel with retry when the calendar failed', () => {
    hooks.useEventCalendar.mockReturnValue(
      fakeQuery(undefined, { isError: true, isPending: false }),
    );
    render(<EventCalendarPanel />);
    expect(screen.getByText('The calendar failed to load.')).toBeInTheDocument();
  });
});
