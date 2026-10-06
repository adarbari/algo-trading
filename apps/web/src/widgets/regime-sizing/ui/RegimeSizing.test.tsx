import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeSizing } from './RegimeSizing';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
}));

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('RegimeSizing', () => {
  it("shows the size per weather, the unknown size and each screener's pauses", async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { container } = render(<RegimeSizing />);
    expect(screen.getByText(/The regime gate is on/)).toBeVisible();
    const sizes = screen.getByLabelText('Size of a new position');
    expect(within(sizes).getByText('Storm').closest('div')).toHaveTextContent('50%');
    expect(within(sizes).getByText('Weather not computed').closest('div')).toHaveTextContent('0%');
    const screeners = screen.getByLabelText('Your screeners');
    expect(within(screeners).getByText('Pauses in Storm and Severe storm')).toBeVisible();
    expect(within(screeners).getByText('Never pauses')).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('says the gate is off, and which screeners have it off', () => {
    const base = regimeFixture().sizing;
    hooks.useRegime.mockReturnValue(
      fakeQuery<Regime | null>(
        regimeFixture({
          sizing: {
            ...base,
            enabled: false,
            screeners: [{ screenerId: 'a', name: 'A', enabled: false, pauseIn: ['STRESS'] }],
          },
        }),
      ),
    );
    render(<RegimeSizing />);
    expect(screen.getByText(/The regime gate is off/)).toBeVisible();
    expect(screen.getByText('Gate off (set to pause in Storm)')).toBeVisible();
  });

  it('is empty without a regime, loading before the answer, an error on failure', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeSizing />);
    expect(screen.getByText('No regime rules are stored yet.')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeSizing />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the regime rules');
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeSizing />);
    expect(screen.getByText('The regime rules failed to load.')).toBeVisible();
  });
});
