import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Disclosure } from './Disclosure';

describe('Disclosure', () => {
  it('toggles the detail region from the summary button (uncontrolled)', async () => {
    render(
      <Disclosure label="No chain published" count="63">
        XMAX · IMDX
      </Disclosure>,
    );
    const button = screen.getByRole('button', { name: 'No chain published 63' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('XMAX · IMDX')).not.toBeVisible();
    await userEvent.setup().click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('XMAX · IMDX')).toBeVisible();
    expect(button.getAttribute('aria-controls')).toBe(screen.getByText('XMAX · IMDX').id);
  });

  it('follows `open` when controlled and reports the requested state', async () => {
    const onOpenChange = vi.fn();
    render(
      <Disclosure label="Stale" open onOpenChange={onOpenChange}>
        detail
      </Disclosure>,
    );
    await userEvent.setup().click(screen.getByRole('button'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens with Enter and Space from the keyboard', async () => {
    render(<Disclosure label="Stale">detail</Disclosure>);
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard(' ');
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Disclosure label="Stale" count="515" defaultOpen>
        ACIU · ALLT
      </Disclosure>,
    );
    await expectNoA11yViolations(container);
  });
});
