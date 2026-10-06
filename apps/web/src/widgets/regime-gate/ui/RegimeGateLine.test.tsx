import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { RegimeGateLine } from './RegimeGateLine';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
}));

beforeEach(() => {
  hooks.useRegime.mockReset();
  hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
});

describe('RegimeGateLine', () => {
  it('says where the screen pauses, links to the Regime page and says it is read-only', async () => {
    const onOpenRegime = vi.fn();
    const { container } = render(
      <RegimeGateLine screenerId="vrp_scanner" onOpenRegime={onOpenRegime} />,
    );
    expect(screen.getByText('This screen pauses in Storm and Severe storm')).toBeVisible();
    expect(screen.getByText(/not editable here/)).toBeVisible();
    await userEvent.setup().click(screen.getByRole('button', { name: 'See the Regime page' }));
    expect(onOpenRegime).toHaveBeenCalledOnce();
    await expectNoA11yViolations(container);
  });

  it('says there is no gate for a screen that pauses nowhere or is not saved', () => {
    const { rerender } = render(<RegimeGateLine screenerId="quiet" onOpenRegime={vi.fn()} />);
    expect(screen.getByText('No regime gate')).toBeVisible();
    rerender(<RegimeGateLine screenerId="unsaved" onOpenRegime={vi.fn()} />);
    expect(screen.getByText('No regime gate')).toBeVisible();
  });

  it('says so when nothing is stored, and when the read failed', () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(null));
    const { rerender } = render(<RegimeGateLine screenerId="x" onOpenRegime={vi.fn()} />);
    expect(screen.getByText('No regime gate')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<RegimeGateLine screenerId="x" onOpenRegime={vi.fn()} />);
    expect(screen.getByText('The regime gate could not be read.')).toBeVisible();
  });
});
