import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Popover, type PopoverProps } from './Popover';

function Example(props: Partial<PopoverProps>) {
  return (
    <>
      <Popover
        label="Filters"
        trigger={(p) => (
          <button type="button" {...p}>
            Filters
          </button>
        )}
        {...props}
      >
        <button type="button">Apply</button>
        <button type="button">Reset</button>
      </Popover>
      <button type="button">Outside</button>
    </>
  );
}

describe('Popover', () => {
  it('opens on click as a named dialog wired to its trigger, focus moves in', async () => {
    const onOpenChange = vi.fn();
    render(<Example onOpenChange={onOpenChange} />);
    const user = userEvent.setup();
    const trigger = screen.getByRole('button', { name: 'Filters' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    await user.click(trigger);
    const panel = screen.getByRole('dialog', { name: 'Filters' });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAttribute('aria-controls', panel.id);
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    const apply = screen.getByRole('button', { name: 'Apply' });
    await waitFor(() => {
      expect(apply).toHaveFocus();
    });
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const trigger = screen.getByRole('button', { name: 'Filters' });
    await user.click(trigger);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('closes on a click outside and on a second trigger click', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const trigger = screen.getByRole('button', { name: 'Filters' });
    await user.click(trigger);
    await user.click(screen.getByRole('button', { name: 'Outside' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(trigger);
    await user.click(trigger);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('follows `open` when controlled', () => {
    const { rerender } = render(<Example open={false} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    rerender(<Example open />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('has no accessibility violations (open)', async () => {
    render(<Example defaultOpen />);
    await expectNoA11yViolations(document.body);
  });
});
