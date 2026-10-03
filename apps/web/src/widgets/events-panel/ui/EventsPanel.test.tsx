import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { EventsPanel } from './EventsPanel';

const hooks = vi.hoisted(() => ({ useInstrumentEvents: vi.fn() }));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentEvents: hooks.useInstrumentEvents,
}));

stubElementSize();

beforeEach(() => {
  hooks.useInstrumentEvents.mockReturnValue(
    fakeQuery([
      { table: 'events/dividend', ts: '2026-08-10T00:00:00+00:00', values: { cash_amount: 0.27 } },
      { table: 'events/earnings', ts: '2026-10-29T00:00:00+00:00', values: { reported: false } },
      {
        table: 'events/split',
        ts: '2020-08-31T00:00:00+00:00',
        values: { split_from: 1, split_to: 4 },
      },
    ]),
  );
});

describe('EventsPanel', () => {
  it('lists events newest first with their kind and detail', async () => {
    const { container } = render(<EventsPanel symbol="AAPL" />);
    const grid = screen.getByRole('grid', { name: 'AAPL events' });
    const rows = within(grid).getAllByRole('row').slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining('29 Oct 2026Earnings'),
      expect.stringContaining('10 Aug 2026Ex-dividend$0.27 cash'),
      expect.stringContaining('31 Aug 2020Split4-for-1'),
    ]);
    await expectNoA11yViolations(container);
  });

  it('says when there are none', () => {
    hooks.useInstrumentEvents.mockReturnValue(fakeQuery([]));
    render(<EventsPanel symbol="KO" />);
    expect(screen.getByText('No stored events for KO.')).toBeInTheDocument();
  });
});
