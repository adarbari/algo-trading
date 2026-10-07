import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { OptionList, type OptionListItem } from './OptionList';

const items: OptionListItem[] = [
  { id: 'a', title: 'bb_squeeze', description: 'Bands inside the channel.' },
  { id: 'b', title: 'atr_ratio', description: 'Short range over long.' },
];

describe('OptionList', () => {
  it('lists each choice with its description and marks the current one', () => {
    render(<OptionList items={items} value="b" onSelect={vi.fn()} label="Fields" />);
    const list = screen.getByRole('list', { name: 'Fields' });
    expect(list.querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByText('Bands inside the channel.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /atr_ratio/ })).toHaveAttribute(
      'aria-current',
      'true',
    );
    expect(screen.getByRole('button', { name: /bb_squeeze/ })).not.toHaveAttribute('aria-current');
  });

  it('reports the id of the choice clicked or activated by keyboard', async () => {
    const onSelect = vi.fn();
    render(<OptionList items={items} value={null} onSelect={onSelect} label="Fields" />);
    await userEvent.click(screen.getByRole('button', { name: /bb_squeeze/ }));
    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(onSelect.mock.calls).toEqual([['a'], ['b']]);
  });

  it('scrolls inside a maximum height and uses the monospace face on request', () => {
    render(
      <OptionList
        items={items}
        value={null}
        onSelect={vi.fn()}
        label="Fields"
        mono
        maxHeight="md"
      />,
    );
    expect(screen.getByRole('list')).toHaveAttribute('data-max-height', 'md');
    expect(screen.getByText('bb_squeeze')).toHaveAttribute('data-mono');
  });

  it('shows loading and empty states', () => {
    const { rerender } = render(
      <OptionList items={[]} value={null} onSelect={vi.fn()} label="Fields" loading />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    rerender(
      <OptionList items={[]} value={null} onSelect={vi.fn()} label="Fields" emptyMessage="None." />,
    );
    expect(screen.getByText('None.')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <OptionList items={items} value="a" onSelect={vi.fn()} label="Fields" mono />,
    );
    await expectNoA11yViolations(container);
  });
});
