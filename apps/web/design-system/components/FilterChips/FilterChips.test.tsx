import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { FilterChips, type FilterChipItem } from './FilterChips';

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

  describe('structured items', () => {
    const ITEMS: FilterChipItem[] = [
      { id: 'a', label: 'Decision', valueText: 'Qualified', removes: 1200, active: true },
      { id: 'b', label: 'DTE', valueText: '..14', removes: 9, unknown: 3, active: false },
      { id: 'c', label: 'Liq', valueText: 'risk', active: true },
    ];

    it('shows removes, unknown and off, and toggles through aria-pressed', async () => {
      const onToggle = vi.fn();
      const { container } = render(
        <FilterChips items={ITEMS} onToggle={onToggle} onRemove={vi.fn()} onClear={vi.fn()} />,
      );
      expect(screen.getByText(/removes 1,200/)).toBeInTheDocument();
      expect(screen.getByText(/3 unknown/)).toBeInTheDocument();
      expect(screen.queryByText(/removes 9/)).toBeNull();
      const off = screen.getByRole('button', { name: /^DTE \.\.14, off/ });
      expect(off).toHaveAttribute('aria-pressed', 'false');
      expect(screen.getByRole('button', { name: /^Decision Qualified/ })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await userEvent.click(off);
      expect(onToggle).toHaveBeenCalledWith('b');
      await expectNoA11yViolations(container);
    });

    it('removes a chip, moves focus to the next one, and clears all', async () => {
      function Held() {
        const [items, setItems] = useState(ITEMS);
        return (
          <FilterChips
            items={items}
            onToggle={vi.fn()}
            onRemove={(id) => {
              setItems((now) => now.filter((i) => i.id !== id));
            }}
            onClear={() => {
              setItems([]);
            }}
          />
        );
      }
      render(<Held />);
      await userEvent.click(screen.getByRole('button', { name: 'Remove Decision Qualified' }));
      expect(screen.getByRole('button', { name: /^DTE/ })).toHaveFocus();
      await userEvent.click(screen.getByRole('button', { name: 'Clear all' }));
      expect(screen.queryByRole('button', { name: /Remove/ })).toBeNull();
    });

    it('moves focus to emptyFocusRef when the last chip goes, and draws Clear all only if passed', async () => {
      function Held() {
        const [items, setItems] = useState(ITEMS.slice(0, 1));
        const target = useRef<HTMLInputElement>(null);
        return (
          <>
            <input ref={target} aria-label="Search" />
            <FilterChips
              items={items}
              emptyFocusRef={target}
              onToggle={vi.fn()}
              onRemove={() => {
                setItems([]);
              }}
            />
          </>
        );
      }
      render(<Held />);
      expect(screen.queryByRole('button', { name: 'Clear all' })).toBeNull();
      await userEvent.click(screen.getByRole('button', { name: 'Remove Decision Qualified' }));
      expect(screen.getByRole('textbox', { name: 'Search' })).toHaveFocus();
    });
  });
});
