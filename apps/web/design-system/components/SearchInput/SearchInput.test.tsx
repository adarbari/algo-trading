import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SearchInput } from './SearchInput';

describe('SearchInput', () => {
  it('is a search box named Search by default', () => {
    render(<SearchInput />);
    expect(screen.getByRole('searchbox', { name: 'Search' })).toBeInTheDocument();
  });

  it('clears with the clear button and with Escape', async () => {
    const onValueChange = vi.fn();
    render(<SearchInput aria-label="Tickers" onValueChange={onValueChange} />);
    const box = screen.getByRole('searchbox', { name: 'Tickers' });
    await userEvent.type(box, 'AAPL');
    expect(box).toHaveValue('AAPL');
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(box).toHaveValue('');
    expect(box).toHaveFocus();
    await userEvent.type(box, 'SPY{Escape}');
    expect(box).toHaveValue('');
    expect(onValueChange).toHaveBeenLastCalledWith('');
  });

  it('submits on Enter', async () => {
    const onSubmit = vi.fn();
    render(<SearchInput onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole('searchbox'), 'QQQ{Enter}');
    expect(onSubmit).toHaveBeenCalledWith('QQQ');
  });

  it('announces loading with a labelled spinner', () => {
    render(<SearchInput loading defaultValue="NV" />);
    expect(screen.getByRole('img', { name: 'Searching' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<SearchInput defaultValue="AAPL" />);
    await expectNoA11yViolations(container);
  });
});
