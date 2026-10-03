import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Tooltip } from './Tooltip';

function Example() {
  return (
    <Tooltip content="Re-run the preview" delay="none">
      {(props) => (
        <button type="button" {...props}>
          Re-run
        </button>
      )}
    </Tooltip>
  );
}

describe('Tooltip', () => {
  it('describes its trigger, shows on focus and hides on Escape', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const button = screen.getByRole('button', { name: 'Re-run' });
    expect(button).toHaveAccessibleDescription('Re-run the preview');
    await user.tab();
    expect(button).toHaveFocus();
    expect(await screen.findByRole('tooltip')).toBeVisible();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('shows on hover and hides when the pointer leaves', async () => {
    render(<Example />);
    const user = userEvent.setup();
    await user.hover(screen.getByRole('button'));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Re-run the preview');
    await user.unhover(screen.getByRole('button'));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Example />);
    await expectNoA11yViolations(container);
  });
});
