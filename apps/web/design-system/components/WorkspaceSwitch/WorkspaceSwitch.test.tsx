import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { WorkspaceSwitch } from './WorkspaceSwitch';

const WORKSPACES = [
  { value: 'trader', label: 'Trader' },
  { value: 'admin', label: 'Admin' },
];

describe('WorkspaceSwitch', () => {
  it('shows the current workspace as checked in a group named Workspace', () => {
    render(<WorkspaceSwitch workspaces={WORKSPACES} value="admin" onValueChange={vi.fn()} />);
    expect(screen.getByRole('radiogroup', { name: 'Workspace' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Admin' })).toHaveAttribute('aria-checked', 'true');
  });

  it('asks the app to switch, by click or arrow key', async () => {
    const onValueChange = vi.fn();
    render(
      <WorkspaceSwitch workspaces={WORKSPACES} value="trader" onValueChange={onValueChange} />,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Admin' }));
    expect(onValueChange).toHaveBeenLastCalledWith('admin');
    screen.getByRole('radio', { name: 'Trader' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onValueChange).toHaveBeenCalledTimes(2);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <WorkspaceSwitch workspaces={WORKSPACES} value="trader" onValueChange={vi.fn()} />,
    );
    await expectNoA11yViolations(container);
  });
});
