import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SortableList } from './SortableList';

const NAMES = ['Liquidity', 'IV rank', 'Earnings'];

function Harness({
  onReorder = () => undefined,
  disabled = false,
}: {
  onReorder?: (names: string[]) => void;
  disabled?: boolean;
}) {
  const [items, setItems] = useState(NAMES);
  return (
    <SortableList
      label="Priority"
      items={items}
      getKey={(name) => name}
      getLabel={(name) => name}
      renderItem={(name) => <span>{name}</span>}
      disabled={disabled}
      onReorder={(next) => {
        setItems(next);
        onReorder(next);
      }}
    />
  );
}

const order = () => screen.getAllByRole('listitem').map((li) => li.textContent);

describe('SortableList', () => {
  it('reorders from the keyboard and announces each move', async () => {
    const onReorder = vi.fn();
    render(<Harness onReorder={onReorder} />);
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Reorder Liquidity' })).toHaveFocus();
    await user.keyboard(' ');
    expect(screen.getByText(/Grabbed Liquidity, position 1 of 3/)).toBeInTheDocument();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(order()).toEqual(['IV rank', 'Earnings', 'Liquidity']);
    expect(screen.getByText('Liquidity moved to position 3 of 3.')).toBeInTheDocument();
    expect(onReorder).not.toHaveBeenCalled();
    await user.keyboard(' ');
    expect(onReorder).toHaveBeenCalledWith(['IV rank', 'Earnings', 'Liquidity']);
    expect(screen.getByText('Liquidity dropped at position 3 of 3.')).toBeInTheDocument();
  });

  it('cancels with Escape and restores the order', async () => {
    const onReorder = vi.fn();
    render(<Harness onReorder={onReorder} />);
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard(' {ArrowDown}{Escape}');
    expect(order()).toEqual(NAMES);
    expect(onReorder).not.toHaveBeenCalled();
    expect(screen.getByText(/Reorder cancelled. Liquidity is at position 1 of 3/)).toBeVisible();
  });

  it('does not move past the ends', async () => {
    render(<Harness />);
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard(' {ArrowUp}');
    expect(order()).toEqual(NAMES);
  });

  it('reorders by dragging a handle with the pointer', async () => {
    const onReorder = vi.fn();
    render(<Harness onReorder={onReorder} />);
    const rows = screen.getAllByRole('listitem');
    // jsdom has no layout: give each row a box 40px tall, stacked.
    rows.forEach((row, i) => {
      row.getBoundingClientRect = () => new DOMRect(0, i * 40, 100, 40);
    });
    const handle = screen.getByRole('button', { name: 'Reorder Liquidity' });
    const user = userEvent.setup();
    await user.pointer([
      { keys: '[MouseLeft>]', target: handle },
      { coords: { clientX: 10, clientY: 70 } },
      { coords: { clientX: 10, clientY: 72 } },
      { keys: '[/MouseLeft]' },
    ]);
    expect(onReorder).toHaveBeenCalledWith(['IV rank', 'Liquidity', 'Earnings']);
  });

  it('is inert when disabled', () => {
    render(<Harness disabled />);
    expect(screen.getByRole('button', { name: 'Reorder Liquidity' })).toBeDisabled();
  });

  it('shows the empty slot when there are no items', () => {
    render(
      <SortableList<string>
        label="Priority"
        items={[]}
        getKey={(n) => n}
        getLabel={(n) => n}
        renderItem={(n) => n}
        onReorder={() => undefined}
        empty={<p>Nothing yet</p>}
      />,
    );
    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Harness />);
    await expectNoA11yViolations(container);
  });
});
