import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LinkButton } from './LinkButton';

describe('LinkButton', () => {
  it('runs its callback and is named by its words, or by aria-label when given', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <LinkButton aria-label="Open Breakout: 12 picks" onClick={onClick}>
        12 picks
      </LinkButton>,
    );
    await userEvent.setup().click(screen.getByRole('button', { name: 'Open Breakout: 12 picks' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    await expectNoA11yViolations(container);
  });

  it('opens with Enter from the keyboard', async () => {
    const onClick = vi.fn();
    render(<LinkButton onClick={onClick}>12 picks</LinkButton>);
    await userEvent.setup().tab();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalled();
  });
});
