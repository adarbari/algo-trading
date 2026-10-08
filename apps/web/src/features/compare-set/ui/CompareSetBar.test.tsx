import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { CompareSetBar } from './CompareSetBar';

describe('CompareSetBar', () => {
  it('shows the set in series order, removes, clears and refocuses', async () => {
    const user = userEvent.setup();
    const handlers = { onRemove: vi.fn(), onClear: vi.fn(), onFocus: vi.fn(), onOpen: vi.fn() };
    const { container } = render(
      <CompareSetBar symbols={['AAPL', 'MSFT']} focused="KO" {...handlers} />,
    );
    await user.click(screen.getByRole('button', { name: 'Remove MSFT from compare' }));
    expect(handlers.onRemove).toHaveBeenCalledWith('MSFT');
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(handlers.onClear).toHaveBeenCalled();
    const focus = screen.getByRole('combobox', { name: 'Ticker shown in the detail tabs' });
    expect(focus).toHaveValue('KO');
    await user.selectOptions(focus, 'AAPL');
    expect(handlers.onFocus).toHaveBeenCalledWith('AAPL');
    await expectNoA11yViolations(container);
  });

  it('opens the detail for the focused ticker, else the first, labelled by the count', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const base = { onRemove: vi.fn(), onClear: vi.fn(), onFocus: vi.fn(), onOpen };
    const { rerender } = render(
      <CompareSetBar symbols={['AAPL', 'MSFT']} focused="MSFT" {...base} />,
    );
    await user.click(screen.getByRole('button', { name: 'Compare 2' }));
    expect(onOpen).toHaveBeenLastCalledWith('MSFT');
    rerender(<CompareSetBar symbols={['AAPL', 'MSFT']} focused={null} {...base} />);
    await user.click(screen.getByRole('button', { name: 'Compare 2' }));
    expect(onOpen).toHaveBeenLastCalledWith('AAPL');
    rerender(<CompareSetBar symbols={['KO']} focused={null} {...base} />);
    expect(screen.getByRole('button', { name: 'Open detail' })).toBeInTheDocument();
  });

  it('explains how to fill an empty set', () => {
    render(
      <CompareSetBar
        symbols={[]}
        focused={null}
        onRemove={vi.fn()}
        onClear={vi.fn()}
        onFocus={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText(/Tick up to 6 tickers/)).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
