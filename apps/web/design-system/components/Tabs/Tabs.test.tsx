import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Tabs } from './Tabs';

const items = [
  { id: 'a', label: 'Compare' },
  { id: 'b', label: 'Chart', disabled: true },
  { id: 'c', label: 'Options', count: 4 },
];

function Harness({ onChange }: { onChange?: (id: string) => void }) {
  const [value, setValue] = useState('a');
  return (
    <Tabs
      items={items}
      value={value}
      label="View"
      onChange={(id) => {
        setValue(id);
        onChange?.(id);
      }}
    >
      Panel {value}
    </Tabs>
  );
}

describe('Tabs', () => {
  it('renders a named tablist with the selected tab and its panel linked', () => {
    render(<Harness />);
    expect(screen.getByRole('tablist', { name: 'View' })).toBeInTheDocument();
    const selected = screen.getByRole('tab', { selected: true });
    expect(selected).toHaveTextContent('Compare');
    expect(selected).toHaveAttribute('tabindex', '0');
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveAccessibleName('Compare');
    expect(selected).toHaveAttribute('aria-controls', panel.id);
  });

  it('moves and selects with arrows, skipping disabled tabs, wrapping, Home / End', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: 'Compare' }));
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Options 4' })).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith('c');
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Compare' })).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{End}');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel c');
    await user.keyboard('{Home}');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel a');
  });

  it('selects on click', async () => {
    render(<Harness />);
    await userEvent.setup().click(screen.getByRole('tab', { name: 'Options 4' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel c');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Harness />);
    await expectNoA11yViolations(container);
  });
});
