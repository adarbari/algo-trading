import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { AccountMenu } from './AccountMenu';

describe('AccountMenu', () => {
  it('opens on the name and offers the content and Sign out', async () => {
    const onSignOut = vi.fn();
    render(
      <AccountMenu name="Bo" onSignOut={onSignOut}>
        <span>workspace switch</span>
      </AccountMenu>,
    );
    expect(screen.queryByText('workspace switch')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Bo' }));
    expect(await screen.findByText('workspace switch')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('shows no Sign out without onSignOut', async () => {
    render(<AccountMenu name="Ann" />);
    await userEvent.click(screen.getByRole('button', { name: 'Ann' }));
    expect(await screen.findByText('Signed in as Ann')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<AccountMenu name="Bo" onSignOut={() => undefined} />);
    await expectNoA11yViolations(container);
  });
});
