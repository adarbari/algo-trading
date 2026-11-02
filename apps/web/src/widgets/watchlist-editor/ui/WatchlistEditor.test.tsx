import { Button, ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MAX_WATCHLIST } from '@/entities/trader-preferences';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { WatchlistEditor } from './WatchlistEditor';

const hooks = vi.hoisted(() => ({ prefs: vi.fn(), mutate: vi.fn() }));
vi.mock('@/entities/trader-preferences', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useTraderPreferences: hooks.prefs,
  useSaveWatchlist: () => ({ mutate: hooks.mutate }),
}));
vi.mock('@/features/ticker-search', () => ({
  TickerSearch: ({ onChoose }: { onChoose: (s: string, id: string) => void }) => (
    <Button
      onClick={() => {
        onChoose('CCC', 'EQ:C');
      }}
    >
      search
    </Button>
  ),
}));

const list = (ids: string[]) => ({
  data: {
    defaultTab: 'stocks',
    watchlist: ids.map((i) => ({ instrumentId: i, symbol: i.slice(3) })),
  },
});

beforeEach(() => {
  hooks.mutate.mockReset();
  hooks.prefs.mockReturnValue(list(['EQ:A', 'EQ:B']));
});

const renderEditor = () =>
  render(
    <ToastProvider>
      <WatchlistEditor />
    </ToastProvider>,
  );

describe('WatchlistEditor', () => {
  it('shows the names as tags and adds a searched one at the end', async () => {
    const { container } = renderEditor();
    expect(screen.getByText('A')).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(screen.getByRole('button', { name: 'search' }));
    expect(hooks.mutate.mock.calls[0]?.[0]).toEqual([
      { instrumentId: 'EQ:A', symbol: 'A' },
      { instrumentId: 'EQ:B', symbol: 'B' },
      { instrumentId: 'EQ:C', symbol: 'CCC' },
    ]);
  });

  it('removes a name, and offers no search at the cap', async () => {
    const { unmount } = renderEditor();
    await userEvent.click(screen.getByRole('button', { name: 'Remove A from the watchlist' }));
    expect(hooks.mutate.mock.calls[0]?.[0]).toEqual([{ instrumentId: 'EQ:B', symbol: 'B' }]);
    unmount();
    hooks.prefs.mockReturnValue(list(Array.from({ length: MAX_WATCHLIST }, (_, n) => `EQ:${n}`)));
    renderEditor();
    expect(screen.queryByRole('button', { name: 'search' })).not.toBeInTheDocument();
  });
});
