import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Toast } from './Toast';
import { ToastProvider, useToast, type ToastOptions } from './ToastProvider';

function Trigger({ options }: { options: ToastOptions }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => {
        toast.show(options);
      }}
    >
      Show
    </button>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('Toast', () => {
  it('is a status with its action; negative is an alert', async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Toast title="Saved" action={{ label: 'Undo', onClick }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
    await userEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onClick).toHaveBeenCalledOnce();
    rerender(<Toast tone="negative" title="Failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');
  });

  it('useToast shows toasts in the notifications region and dismisses them after the duration', () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger options={{ title: 'Saved', duration: 1000 }} />
      </ToastProvider>,
    );
    act(() => {
      screen.getByRole('button', { name: 'Show' }).click();
    });
    const region = screen.getByRole('region', { name: 'Notifications' });
    expect(region).toHaveTextContent('Saved');
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(region).not.toHaveTextContent('Saved');
  });

  it('keeps negative toasts until dismissed, and keeps at most three', async () => {
    render(
      <ToastProvider>
        <Trigger options={{ title: 'Failed', tone: 'negative' }} />
      </ToastProvider>,
    );
    const user = userEvent.setup();
    for (let i = 0; i < 4; i += 1) await user.click(screen.getByRole('button', { name: 'Show' }));
    expect(screen.getAllByRole('alert')).toHaveLength(3);
    await user.click(screen.getAllByRole('button', { name: 'Dismiss' })[0] as HTMLElement);
    expect(screen.getAllByRole('alert')).toHaveLength(2);
  });

  it('throws a helpful error outside the provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Trigger options={{ title: 'x' }} />)).toThrow(/ToastProvider/);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ToastProvider>
        <Toast title="Saved" onDismiss={vi.fn()} />
      </ToastProvider>,
    );
    await expectNoA11yViolations(container);
  });
});
