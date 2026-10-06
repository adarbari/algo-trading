import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { regimeFixture, unknownRegimeFixture } from '../model/fixtures';
import type { Regime } from '../model/regime';

import { RegimeChip } from './RegimeChip';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('../api/hooks', () => ({ useRegime: hooks.useRegime }));

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('RegimeChip', () => {
  it('shows the weather word, the headline on hover, and opens the Regime page', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const onOpen = vi.fn();
    const { container } = render(<RegimeChip onOpen={onOpen} />);
    const chip = screen.getByRole('button', { name: 'Regime: Clouds building' });
    expect(screen.getByText('Regime: Clouds building')).toHaveAttribute(
      'title',
      '1 of 3 warning signs is on. The fast signs are quiet.',
    );
    expect(screen.getByText('Regime: Clouds building')).toHaveAttribute('data-tone', 'warning');
    await userEvent.setup().click(chip);
    expect(onOpen).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });

  it('says "not computed" for an UNKNOWN regime, muted, never hidden', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(unknownRegimeFixture()));
    render(<RegimeChip onOpen={vi.fn()} />);
    expect(screen.getByText('Regime: not computed')).toHaveAttribute('data-tone', 'neutral');
  });

  it('says "not computed" when nothing is stored for the session', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    render(<RegimeChip onOpen={vi.fn()} />);
    expect(screen.getByText('Regime: not computed')).toBeVisible();
  });

  it('says it is unavailable when the read failed, and shows a skeleton while loading', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    const { rerender } = render(<RegimeChip onOpen={vi.fn()} />);
    expect(screen.getByText('Regime: unavailable')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<RegimeChip onOpen={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the market regime');
  });
});
