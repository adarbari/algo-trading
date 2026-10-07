import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Drawer, type DrawerProps } from './Drawer';

function Example(props: Partial<DrawerProps>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Details
      </button>
      <Drawer open={open} onOpenChange={setOpen} title="AAPL · Apple" {...props}>
        <a href="#explore">Open in Explore</a>
      </Drawer>
    </>
  );
}

describe('Drawer', () => {
  it('opens as a modal dialog on the end side and returns focus on close', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'Details' });
    await user.click(opener);
    const drawer = screen.getByRole('dialog', { name: 'AAPL · Apple' });
    expect(drawer).toHaveAttribute('aria-modal', 'true');
    expect(drawer).toHaveAttribute('data-kind', 'drawer');
    expect(drawer).toHaveAttribute('data-side', 'end');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('opens from the start side', async () => {
    render(<Example side="start" />);
    await userEvent.click(screen.getByRole('button', { name: 'Details' }));
    expect(screen.getByRole('dialog')).toHaveAttribute('data-side', 'start');
  });

  it('shows an eyebrow above the title without making it part of the name', async () => {
    render(<Example eyebrow="rollup.momentum@v1.rel_volume" />);
    await userEvent.click(screen.getByRole('button', { name: 'Details' }));
    const drawer = screen.getByRole('dialog', { name: 'AAPL · Apple' });
    expect(drawer).toHaveTextContent('rollup.momentum@v1.rel_volume');
  });

  it('has no accessibility violations (open)', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Details' }));
    await expectNoA11yViolations(document.body);
  });
});
