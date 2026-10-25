import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ThemeChoice } from './ThemeChoice';

const hooks = vi.hoisted(() => ({ useTheme: vi.fn(), mutate: vi.fn() }));
vi.mock('@/entities/appearance', () => ({
  useTheme: hooks.useTheme,
  useSaveTheme: () => ({ mutate: hooks.mutate }),
  readDeviceTheme: () => undefined,
}));
vi.mock('@/features/guide-help', () => ({
  Labelled: ({ text, help }: { text: string; help: string }) => `${text} (help ${help})`,
}));

beforeEach(() => {
  hooks.useTheme.mockReturnValue('light');
  hooks.mutate.mockReset();
});

const renderChoice = () =>
  render(
    <ToastProvider>
      <ThemeChoice />
    </ToastProvider>,
  );

describe('ThemeChoice', () => {
  it('shows the stored choice, with its Guide help, and saves a change', async () => {
    renderChoice();
    expect(screen.getByText('Theme (help theme)')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Light' })).toBeChecked();
    await userEvent.click(screen.getByRole('radio', { name: 'System' }));
    expect(hooks.mutate).toHaveBeenCalledWith('system', expect.anything());
  });

  it('says so when the save fails', async () => {
    hooks.mutate.mockImplementation((_theme: string, options: { onError: () => void }) => {
      options.onError();
    });
    renderChoice();
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(await screen.findByText(/Theme not saved/)).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderChoice();
    await expectNoA11yViolations(container);
  });
});
