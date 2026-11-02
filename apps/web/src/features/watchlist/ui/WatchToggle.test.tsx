import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MAX_WATCHLIST } from '@/entities/trader-preferences';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { WatchToggle } from './WatchToggle';

const hooks = vi.hoisted(() => ({ prefs: vi.fn(), mutate: vi.fn() }));
vi.mock('@/entities/trader-preferences', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useTraderPreferences: hooks.prefs,
  useSaveWatchlist: () => ({ mutate: hooks.mutate }),
}));

const watching = (ids: string[]) => ({
  data: { defaultTab: 'stocks', watchlist: ids.map((i) => ({ instrumentId: i, symbol: i })) },
});

beforeEach(() => {
  hooks.mutate.mockReset();
});

const renderToggle = () =>
  render(
    <ToastProvider>
      <WatchToggle instrumentId="EQ:B" symbol="BBB" />
    </ToastProvider>,
  );

describe('WatchToggle', () => {
  it('adds the name after the ones watched, as an instrument id with its ticker', async () => {
    hooks.prefs.mockReturnValue(watching(['EQ:A']));
    const { container } = renderToggle();
    const button = screen.getByRole('button', { name: 'Watch BBB' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    await expectNoA11yViolations(container);
    await userEvent.click(button);
    expect(hooks.mutate).toHaveBeenCalledWith(
      [
        { instrumentId: 'EQ:A', symbol: 'EQ:A' },
        { instrumentId: 'EQ:B', symbol: 'BBB' },
      ],
      expect.anything(),
    );
  });

  it('takes a watched name off when pressed again', async () => {
    hooks.prefs.mockReturnValue(watching(['EQ:A', 'EQ:B']));
    renderToggle();
    const button = screen.getByRole('button', { name: 'Watch BBB' });
    expect(button).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(button);
    expect(hooks.mutate).toHaveBeenCalledWith(
      [{ instrumentId: 'EQ:A', symbol: 'EQ:A' }],
      expect.anything(),
    );
  });

  it('is off until the list is known and at the cap for a new name', () => {
    hooks.prefs.mockReturnValue({ data: undefined });
    const { unmount } = renderToggle();
    expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeDisabled();
    unmount();
    hooks.prefs.mockReturnValue(
      watching(Array.from({ length: MAX_WATCHLIST }, (_, n) => `EQ:${n}`)),
    );
    renderToggle();
    expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeDisabled();
  });
});
