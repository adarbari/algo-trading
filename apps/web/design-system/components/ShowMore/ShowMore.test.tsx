import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ShowMore } from './ShowMore';

describe('ShowMore', () => {
  it('says how far the list has come and asks for the next page on a click', async () => {
    const onMore = vi.fn();
    render(<ShowMore shown={50} total={312} onMore={onMore} />);
    expect(screen.getByRole('status')).toHaveTextContent('Showing 50 of 312');
    await userEvent.click(screen.getByRole('button', { name: 'Show 50 more' }));
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it('names the size of a last page shorter than a full one', () => {
    render(<ShowMore shown={300} total={312} onMore={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Show 12 more' })).toBeInTheDocument();
  });

  it('is busy while the next page loads and ignores clicks', async () => {
    const onMore = vi.fn();
    render(<ShowMore shown={50} total={312} status="loading" onMore={onMore} />);
    const button = screen.getByRole('button', { name: /Show 50 more/ });
    expect(button).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(button);
    expect(onMore).not.toHaveBeenCalled();
  });

  it('says the page failed and offers a retry', async () => {
    const onMore = vi.fn();
    render(<ShowMore shown={50} total={312} status="error" onMore={onMore} />);
    expect(screen.getByRole('status')).toHaveTextContent('the next page failed to load');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it('is a line only when every row is shown', () => {
    render(<ShowMore shown={312} total={312} onMore={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('All 312 shown');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('has no accessibility violations in any state', async () => {
    for (const status of ['idle', 'loading', 'error'] as const) {
      const { container, unmount } = render(
        <ShowMore shown={50} total={312} status={status} onMore={vi.fn()} />,
      );
      await expectNoA11yViolations(container);
      unmount();
    }
  });
});
