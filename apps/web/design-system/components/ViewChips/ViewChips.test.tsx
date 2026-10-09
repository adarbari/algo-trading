import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ViewChips } from './ViewChips';

const VIEWS = [
  { value: 'top', label: 'Top today' },
  { value: 'conviction', label: 'High conviction' },
];

describe('ViewChips', () => {
  it('presses the view in use and reports the one chosen', async () => {
    const onValueChange = vi.fn();
    const { container } = render(
      <ViewChips views={VIEWS} value="top" onValueChange={onValueChange} />,
    );
    expect(screen.getByRole('button', { name: 'Top today' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'High conviction' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    await userEvent.click(screen.getByRole('button', { name: 'High conviction' }));
    expect(onValueChange).toHaveBeenCalledWith('conviction');
    await expectNoA11yViolations(container);
  });
});
