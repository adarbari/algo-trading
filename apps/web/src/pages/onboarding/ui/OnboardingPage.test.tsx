import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { OnboardingPage } from './OnboardingPage';

const hooks = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock('@/entities/trader-preferences', () => ({
  useSaveIdeasTab: () => ({ mutate: hooks.mutate }),
}));
vi.mock('@/features/guide-help', () => ({
  Labelled: ({ text, help }: { text: string; help: string }) => `${text} (help ${help})`,
}));

beforeEach(() => {
  hooks.mutate.mockReset();
  hooks.mutate.mockImplementation((_tab: string, options: { onSuccess: () => void }) => {
    options.onSuccess();
  });
});

const renderPage = (onDone = vi.fn()) => {
  render(
    <ToastProvider>
      <OnboardingPage onDone={onDone} />
    </ToastProvider>,
  );
  return onDone;
};

describe('OnboardingPage', () => {
  it('asks one question with its Guide help and saves the answer as the start tab', async () => {
    const onDone = renderPage();
    expect(screen.getByText(/trade_mix/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Mostly options/ }));
    expect(hooks.mutate).toHaveBeenCalledWith('premium', expect.anything());
    expect(onDone).toHaveBeenCalled();
  });

  it('answers shares for Start with shares, and has no accessibility violations', async () => {
    const onDone = renderPage();
    await userEvent.click(screen.getByRole('button', { name: 'Start with shares' }));
    expect(hooks.mutate).toHaveBeenCalledWith('stocks', expect.anything());
    expect(onDone).toHaveBeenCalled();
    const { container } = render(
      <ToastProvider>
        <OnboardingPage onDone={vi.fn()} />
      </ToastProvider>,
    );
    await expectNoA11yViolations(container);
  });

  it('says so and stays when the save fails', async () => {
    hooks.mutate.mockImplementation((_tab: string, options: { onError: () => void }) => {
      options.onError();
    });
    const onDone = renderPage();
    await userEvent.click(screen.getByRole('button', { name: /Mostly shares/ }));
    expect(await screen.findByText(/Not saved/)).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });
});
