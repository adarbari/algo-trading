import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ExpandLink } from './ExpandLink';

describe('ExpandLink', () => {
  it('reports aria-expanded and asks for the opposite state on click', async () => {
    const onOpenChange = vi.fn();
    render(
      <ExpandLink open={false} onOpenChange={onOpenChange}>
        Win 58% vs 51% base
      </ExpandLink>,
    );
    const button = screen.getByRole('button', { name: 'Win 58% vs 51% base' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(button);
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('names the block it controls only while open', async () => {
    const { container, rerender } = render(
      <ExpandLink open controls="block" onOpenChange={() => undefined}>
        Win
      </ExpandLink>,
    );
    expect(screen.getByRole('button')).toHaveAttribute('aria-controls', 'block');
    rerender(
      <ExpandLink open={false} controls="block" onOpenChange={() => undefined}>
        Win
      </ExpandLink>,
    );
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-controls');
    await expectNoA11yViolations(container);
  });
});
