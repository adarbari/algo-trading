import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ErrorState } from './ErrorState';

describe('ErrorState', () => {
  it('is an alert with the message, detail and a working Retry', async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Failed" message="Try again" detail="HTTP 503" onRetry={onRetry} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Failed');
    expect(alert).toHaveTextContent('HTTP 503');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('blocks Retry while retrying', async () => {
    const onRetry = vi.fn();
    render(<ErrorState onRetry={onRetry} retrying />);
    const button = screen.getByRole('button', { name: 'Retry' });
    expect(button).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(button);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ErrorState message="m" onRetry={vi.fn()} />);
    await expectNoA11yViolations(container);
  });
});
