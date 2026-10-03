import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Dialog, type DialogProps } from './Dialog';

function Example(props: Partial<DialogProps>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Rename
      </button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Rename screener"
        description="Names are shown on the Ideas board."
        footer={<button type="button">Save</button>}
        {...props}
      >
        <input aria-label="Name" />
      </Dialog>
    </>
  );
}

describe('Dialog', () => {
  it('opens as a named, described modal dialog with focus inside', async () => {
    render(<Example />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Rename' }));
    const dialog = screen.getByRole('dialog', { name: 'Rename screener' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription('Names are shown on the Ideas board.');
    const name = screen.getByRole('textbox', { name: 'Name' });
    await waitFor(() => {
      expect(name).toHaveFocus();
    });
  });

  it('traps Tab inside and returns focus to the opener on Escape', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'Rename' });
    await user.click(opener);
    await screen.findByRole('dialog');
    for (let i = 0; i < 4; i += 1) {
      await user.tab();
      // Floating UI's focus guards move focus back into the dialog on the next frame.
      await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
      expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement);
    }
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('closes from the close button', async () => {
    render(<Example />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Rename' }));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('ignores Escape when not dismissible', async () => {
    render(<Example dismissible={false} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Rename' }));
    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('has no accessibility violations (open)', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));
    await expectNoA11yViolations(document.body);
  });
});
