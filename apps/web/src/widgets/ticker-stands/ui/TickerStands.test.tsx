import { Text } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { TickerStands } from './TickerStands';

const hooks = vi.hoisted(() => ({ useInstrumentFacts: vi.fn(), usePickedBy: vi.fn() }));

vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrumentFacts: hooks.useInstrumentFacts,
  usePickedBy: hooks.usePickedBy,
}));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
}));

const served = (name: string, value: unknown, format: string, nullMeaning = 'none on file') => ({
  name,
  value,
  unknown: null,
  info: { format, unit: null, dtype: 'float', nullMeaning },
});

const FACTS = {
  instrument: {
    features: [
      served('rollup.earnings@v1.next_earnings_date', '2027-01-28', 'DATE'),
      served('rollup.implied_move@v1.implied_move', 0.061, 'PERCENT'),
      served('rollup.filing_events@v1.sessions_since_late_filing', null, 'NUMBER', 'no notice'),
    ],
  },
};

beforeEach(() => {
  hooks.useInstrumentFacts.mockReturnValue(fakeQuery(FACTS));
  hooks.usePickedBy.mockReturnValue(
    fakeQuery([
      {
        edgeId: 'earnings_drift',
        edgeName: 'Earnings drift',
        tab: 'stocks',
        level: 'promising',
        place: 2,
      },
    ]),
  );
});

describe('TickerStands', () => {
  it('lists the setups that picked it, linked, with the verdict and place', async () => {
    const { container } = render(<TickerStands symbol="ACME" />);
    expect(
      screen.getByRole('heading', { level: 2, name: 'Where ACME stands' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Earnings drift' })).toHaveAttribute(
      'href',
      '/edges?edge=earnings_drift',
    );
    expect(screen.getByText('Promising')).toBeInTheDocument();
    expect(screen.getByText('Place 2 in stocks')).toBeInTheDocument();
    for (const id of [
      'ticker_where_it_stands',
      'ticker_picked_by',
      'ticker_avoid_checks',
      'ticker_next_report',
    ]) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
    await expectNoA11yViolations(container);
  });

  it('says none tonight, with the way to the setups, when no setup picked it', () => {
    hooks.usePickedBy.mockReturnValue(fakeQuery([]));
    render(<TickerStands symbol="ACME" />);
    expect(screen.getByText('None tonight')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: "See every setup's rules" })).toHaveAttribute(
      'href',
      '/edges',
    );
  });

  it('shows each check with its value, None with its meaning, or Unknown when not served, and the priced move', () => {
    render(<TickerStands symbol="ACME" />);
    const checks = screen.getByRole('region', { name: 'Avoid-list checks' });
    const late = within(checks)
      .getByText('Sessions since a late-filing notice')
      .closest('dt')?.parentElement;
    expect(late).toHaveTextContent('None');
    expect(late).toHaveTextContent('no notice');
    expect(
      within(checks).getByText('Short interest, days to cover').closest('dt')?.parentElement,
    ).toHaveTextContent('Unknown');
    const next = screen.getByRole('region', { name: 'Report ahead' });
    expect(next).toHaveTextContent('6.1%');
  });

  it('shows loading and error states with a retry', () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useInstrumentFacts.mockReturnValue(failed);
    hooks.usePickedBy.mockReturnValue(fakeQuery(undefined));
    render(<TickerStands symbol="ACME" />);
    expect(screen.getByText('Loading the setups…')).toBeInTheDocument();
    expect(screen.getAllByText('The checks failed to load.').length).toBe(1);
  });
});
