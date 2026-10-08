import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TickerFilterBar } from './TickerFilterBar';

vi.mock('./MoreFilters', () => ({
  MoreFilters: () => null,
}));

describe('TickerFilterBar', () => {
  it('toggles a quick chip into the filters', async () => {
    const onChange = vi.fn();
    render(<TickerFilterBar filters={{ q: 'ab' }} onChange={onChange} />);
    await userEvent.click(screen.getByRole('button', { name: 'Optionable' }));
    expect(onChange).toHaveBeenCalledWith({ q: 'ab', optionable: true });
  });

  it('shows the many-valued filters in force as removable chips', async () => {
    const onChange = vi.fn();
    render(<TickerFilterBar filters={{ sector: 'Energy' }} onChange={onChange} />);
    expect(screen.getByText('Sector: Energy')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /remove.*sector/i }));
    expect(onChange).toHaveBeenCalledWith({ sector: undefined });
  });

  it('shows no active chips when none is set', () => {
    render(<TickerFilterBar filters={{ q: 'x' }} onChange={vi.fn()} />);
    expect(screen.queryByText(/^Sector:/)).not.toBeInTheDocument();
  });
});
