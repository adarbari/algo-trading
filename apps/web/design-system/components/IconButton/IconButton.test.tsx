import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { IconButton } from './IconButton';

describe('IconButton', () => {
  it('is named by its required label, also shown as a tooltip', () => {
    render(<IconButton icon="close" label="Remove criterion" />);
    const button = screen.getByRole('button', { name: 'Remove criterion' });
    expect(button).toHaveAttribute('title', 'Remove criterion');
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('calls onClick', async () => {
    const onClick = vi.fn();
    render(<IconButton icon="refresh" label="Refresh" onClick={onClick} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <IconButton icon="close" label="Remove" />
        <IconButton icon="columns" label="Columns" variant="secondary" size="sm" />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
