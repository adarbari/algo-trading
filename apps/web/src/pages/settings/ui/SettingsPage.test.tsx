import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SettingsPage } from './SettingsPage';

const hooks = vi.hoisted(() => ({
  prefs: vi.fn(),
  saveTab: vi.fn(),
  signOut: vi.fn(),
  session: vi.fn(),
}));
vi.mock('@/entities/trader-preferences', () => ({
  useTraderPreferences: hooks.prefs,
  useSaveIdeasTab: () => ({ mutate: hooks.saveTab }),
}));
vi.mock('@/entities/viewer', () => ({
  useSession: hooks.session,
  useSignOut: () => hooks.signOut,
}));
vi.mock('@/features/guide-help', () => ({
  Labelled: ({ text, help }: { text: string; help: string }) => `${text} (help ${help})`,
}));
vi.mock('@/widgets/theme-choice', () => ({ ThemeChoice: () => 'theme choice' }));
vi.mock('@/widgets/watchlist-editor', () => ({ WatchlistEditor: () => 'watchlist editor' }));

beforeEach(() => {
  hooks.saveTab.mockReset();
  hooks.signOut.mockReset();
  hooks.prefs.mockReturnValue({ data: { defaultTab: 'premium', watchlist: [] } });
  hooks.session.mockReturnValue({ session: { user: 'ann' } });
});

describe('SettingsPage', () => {
  it('lists the controls with their Guide help and the country read-only', async () => {
    const { container } = render(<SettingsPage />);
    for (const text of [
      'theme choice',
      'Start tab (help start_tab)',
      'watchlist editor',
      'Country (help country)',
      'United States',
    ]) {
      expect(screen.getByText(new RegExp(text.replace(/[()]/g, '\\$&')))).toBeInTheDocument();
    }
    expect(screen.getByText(/Watchlist \(help watchlist\)/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Premium' })).toBeChecked();
    await expectNoA11yViolations(container);
  });

  it('saves a new start tab', async () => {
    render(<SettingsPage />);
    await userEvent.click(screen.getByRole('radio', { name: 'Stocks' }));
    expect(hooks.saveTab).toHaveBeenCalledWith('stocks');
  });

  it('signs out, and offers it only with a session', async () => {
    const { unmount } = render(<SettingsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(hooks.signOut).toHaveBeenCalled();
    unmount();
    hooks.session.mockReturnValue({ session: null });
    render(<SettingsPage />);
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();
  });
});
