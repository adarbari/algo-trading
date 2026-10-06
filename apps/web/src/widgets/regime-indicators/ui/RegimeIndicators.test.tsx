import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, unknownRegimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeIndicators } from './RegimeIndicators';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
}));

vi.mock('@/features/regime-explain', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    ExplainRegime: ({ card }: { card?: string }) => (
      <Button>{`Explain ${card ?? 'the regime'}`}</Button>
    ),
  };
});

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('RegimeIndicators', () => {
  it('lists the slow and the fast cards in their own lists', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { container } = render(<RegimeIndicators />);
    const slow = screen.getByRole('region', { name: 'Slow-moving warning signs' });
    const fast = screen.getByRole('region', { name: 'Fast-moving market signs' });
    expect(within(slow).getAllByRole('listitem')).toHaveLength(2);
    expect(within(fast).getAllByRole('listitem')).toHaveLength(1);
    expect(within(slow).getByText('Is the yield curve inverted?')).toBeVisible();
    expect(within(fast).getByText('Is fear rising?')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('opens a card to its why, history, lead time, false alarms and links', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(
      screen.getByText('An inverted curve has come before every recent recession.'),
    ).not.toBeVisible();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /Is the yield curve inverted/ }));
    expect(
      screen.getByText('An inverted curve has come before every recent recession.'),
    ).toBeVisible();
    expect(screen.getByText('2008: Inverted for 16 months before the fall.')).toBeVisible();
    expect(screen.getByText('Lead time: 6 to 24 months')).toBeVisible();
    expect(screen.getByText('False alarms: Few, but it can be early by two years.')).toBeVisible();
    expect(screen.getByRole('link', { name: /FRED: 10y minus 3m spread/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/series/T10Y3M',
    );
  });

  it('marks a changed card and shows the reason of an UNKNOWN value', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.getByText(/Turned on this week/)).toBeInTheDocument();
    expect(screen.getByText(/Unknown: no market row for 2026-10-02/)).toBeVisible();
  });

  it('shows every card UNKNOWN with its reason when the regime is not computed', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.getAllByText(/Unknown: not stored for this session/)).toHaveLength(3);
  });

  it('is empty when nothing is stored, loading before the answer, an error on failure', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeIndicators />);
    expect(screen.getByText(/there are no warning signs to show/)).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeIndicators />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the warning signs');
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeIndicators />);
    expect(screen.getByText('The warning signs failed to load.')).toBeVisible();
  });

  it('offers to explain each card when the regime is computed, and not when it is not', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { unmount } = render(<RegimeIndicators />);
    expect(screen.getAllByRole('button', { name: /^Explain /, hidden: true })).toHaveLength(3);
    unmount();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeIndicators />);
    expect(screen.queryByRole('button', { name: /^Explain /, hidden: true })).toBeNull();
  });
});
