import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, unknownRegimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeHeader } from './RegimeHeader';

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

describe('RegimeHeader', () => {
  it('shows the headline and what changed this week', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { container } = render(<RegimeHeader />);
    expect(screen.getByRole('heading', { level: 3, name: 'Clouds building' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'What changed this week' })).toBeVisible();
    expect(screen.getByText('Are financial conditions tight?')).toBeVisible();
    expect(screen.getByText('Now on')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Explain the regime' })).toBeVisible();
    expect(screen.queryByText('Is the yield curve inverted?')).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('says nothing changed when no card turned on or off', () => {
    const regime = regimeFixture();
    hooks.useRegime.mockReturnValue(
      fakeQuery<Regime | null>({
        ...regime,
        indicators: regime.indicators.map((i) => ({ ...i, changed: false })),
      }),
    );
    render(<RegimeHeader />);
    expect(screen.getByText(/No warning sign turned on or off/)).toBeVisible();
  });

  it('shows the UNKNOWN state with its reason, not a guess', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeHeader />);
    expect(screen.getByRole('heading', { level: 3, name: 'Not computed' })).toBeVisible();
    expect(screen.getAllByText('not available because of a system error')[0]).toBeVisible();
    expect(screen.getByText('Nothing to compare: the regime is not computed.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Explain the regime' })).toBeNull();
  });

  it('is empty when nothing is stored, loading before the answer', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeHeader />);
    expect(
      screen.getByText('No regime is stored yet, so there is no weather to show.'),
    ).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeHeader />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the market regime');
  });

  it('shows an error with a retry', async () => {
    const query = fakeQuery<Regime | null>(undefined, { isError: true });
    hooks.useRegime.mockReturnValue(query);
    render(<RegimeHeader />);
    expect(screen.getByText('The market regime failed to load.')).toBeVisible();
    await userEvent.setup().click(screen.getByRole('button', { name: /retry/i }));
    expect(query.refetch).toHaveBeenCalledOnce();
  });
});
