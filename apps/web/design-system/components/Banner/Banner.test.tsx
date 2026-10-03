import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Banner } from './Banner';

describe('Banner', () => {
  it('is a status with its title and message; negative is an alert', () => {
    const { rerender } = render(<Banner title="Note">Delayed quotes</Banner>);
    expect(screen.getByRole('status')).toHaveTextContent('NoteDelayed quotes');
    rerender(<Banner tone="negative" title="Run failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Run failed');
  });

  it('reads as the stale-data notice with asOf, in the warning tone', () => {
    const { container } = render(<Banner asOf="2026-10-01">Yesterday’s features</Banner>);
    expect(screen.getByText('Stale data · as of 1 Oct 2026')).toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute('data-tone', 'warning');
  });

  it('can be dismissed', async () => {
    const onDismiss = vi.fn();
    render(<Banner title="x" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Banner title="One">Message</Banner>
        <Banner tone="warning" asOf="2026-10-01" onDismiss={vi.fn()} />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
