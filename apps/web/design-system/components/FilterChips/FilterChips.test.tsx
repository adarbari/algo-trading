import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { FilterChips } from './FilterChips';

const FILTERS = [
  {
    id: 'screener',
    label: 'Screener',
    options: [
      { value: 'vrp', label: 'VRP scanner' },
      { value: 'mr', label: 'Mean reversion' },
    ],
  },
  { id: 'liq', label: 'Liquidity', options: [{ value: 'low', label: 'Low' }] },
];

describe('FilterChips', () => {
  it('offers each filter not in force as an add button, and no Clear filters', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FilterChips filters={FILTERS} values={{}} onChange={onChange} onClear={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Screener' }));
    await userEvent.click(screen.getByRole('button', { name: 'VRP scanner' }));
    expect(onChange).toHaveBeenCalledWith('screener', 'vrp');
    await expectNoA11yViolations(container);
  });

  it('shows a filter in force as a removable chip and clears them all', async () => {
    const onChange = vi.fn();
    const onClear = vi.fn();
    render(
      <FilterChips
        filters={FILTERS}
        values={{ screener: 'vrp' }}
        onChange={onChange}
        onClear={onClear}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Screener' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Remove Screener: VRP scanner' }));
    expect(onChange).toHaveBeenCalledWith('screener', undefined);
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});
