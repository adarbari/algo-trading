import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, unknownRegimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeStrip } from './RegimeStrip';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => {
  const { Button } = await import('@algotrade/ui');
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useRegime: hooks.useRegime,
    // The chip reads the entity's own hook, which is tested with it: a stub keeps this to the strip.
    RegimeChip: (props: { onOpen: () => void }) => (
      <Button onClick={props.onOpen}>regime chip</Button>
    ),
  };
});

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('RegimeStrip', () => {
  it('shows the chip, the sentence and the sizing rule, and opens the Regime page', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const onOpen = vi.fn();
    const { container } = render(<RegimeStrip onOpen={onOpen} />);
    expect(screen.getByText('1 of 3 warning signs is on. The fast signs are quiet.')).toBeVisible();
    expect(screen.getByText('New positions sized at 75% (clouds building)')).toBeVisible();
    await userEvent.setup().click(screen.getByRole('button', { name: 'regime chip' }));
    expect(onOpen).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });

  it('says 100% and that the regime is not computed while it is UNKNOWN', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeStrip onOpen={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'regime chip' })).toBeVisible();
    expect(screen.getByText('New positions sized at 100% (regime not computed)')).toBeVisible();
  });

  it('says so when nothing is stored, while loading and when the read failed', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeStrip onOpen={vi.fn()} />);
    expect(screen.getByText('No regime is stored yet.')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeStrip onOpen={vi.fn()} />);
    expect(screen.getByText('The market regime could not be read.')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeStrip onOpen={vi.fn()} />);
    expect(screen.getByText('Reading the market regime…')).toBeVisible();
  });
});
