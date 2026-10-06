import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { regimeFixture, type Regime } from '@/entities/regime';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { ReadingList } from './ReadingList';

const hooks = vi.hoisted(() => ({ useRegime: vi.fn() }));
vi.mock('@/entities/regime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useRegime: hooks.useRegime,
}));

beforeEach(() => {
  hooks.useRegime.mockReset();
});

describe('ReadingList', () => {
  it('lists each link of the cards once, with the cards that cite it', async () => {
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(regimeFixture()));
    const { container } = render(<ReadingList />);
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /Chicago Fed NFCI/ })).toBeVisible();
    expect(
      screen.getByText('Cited by: Are financial conditions tight?, Is fear rising?'),
    ).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('is empty without links, loading before the answer, an error on failure', () => {
    const regime = regimeFixture();
    hooks.useRegime.mockReturnValue(
      fakeQuery<Regime | null>({
        ...regime,
        indicators: regime.indicators.map((i) => ({ ...i, links: [] })),
      }),
    );
    const { rerender } = render(<ReadingList />);
    expect(screen.getByText('No indicator card cites a link yet.')).toBeVisible();
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined));
    rerender(<ReadingList />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading the reading list');
    hooks.useRegime.mockReturnValue(fakeQuery<Regime | null>(undefined, { isError: true }));
    rerender(<ReadingList />);
    expect(screen.getByText('The reading list failed to load.')).toBeVisible();
  });
});
