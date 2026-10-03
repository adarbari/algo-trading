import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TickerTag } from './TickerTag';

describe('TickerTag', () => {
  it('shows the symbol keyed to its series', () => {
    const { container } = render(<TickerTag symbol="MSFT" series="s2" name="Microsoft" />);
    const tag = container.firstElementChild;
    expect(tag).toHaveAttribute('data-series', 's2');
    expect(tag).toHaveAttribute('title', 'Microsoft');
    expect(screen.getByText('MSFT')).toBeInTheDocument();
  });

  it('removes with a button naming the symbol and context', async () => {
    const onRemove = vi.fn();
    render(<TickerTag symbol="NVDA" onRemove={onRemove} removeContext="from compare" />);
    await userEvent.click(screen.getByRole('button', { name: 'Remove NVDA from compare' }));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <TickerTag symbol="AAPL" series="s1" onRemove={vi.fn()} />
        <TickerTag symbol="KO" />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
