import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ActionGroup } from './ActionGroup';

const onRun = vi.fn();
const ACTIONS = [
  { id: 'run', label: 'Run again', icon: 'refresh', onClick: onRun },
  { id: 'columns', label: 'Columns', icon: 'columns', onClick: vi.fn() },
] as const;

describe('ActionGroup', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    onRun.mockClear();
  });

  it('renders a text button per action on a wide width', async () => {
    vi.stubGlobal('innerWidth', 1400);
    const { container } = render(<ActionGroup actions={ACTIONS} />);
    const button = screen.getByRole('button', { name: 'Run again' });
    expect(button).toHaveTextContent('Run again');
    await userEvent.click(button);
    expect(onRun).toHaveBeenCalledTimes(1);
    await expectNoA11yViolations(container);
  });

  it('renders icon buttons named by the label, with a tooltip on focus, on a narrow width', async () => {
    vi.stubGlobal('innerWidth', 375);
    const { container } = render(<ActionGroup actions={ACTIONS} />);
    const button = screen.getByRole('button', { name: 'Run again' });
    expect(button).not.toHaveTextContent('Run again');
    await userEvent.tab();
    expect(button).toHaveFocus();
    expect(screen.getByRole('tooltip', { name: 'Run again' })).toBeVisible();
    await userEvent.click(button);
    expect(onRun).toHaveBeenCalledTimes(1);
    await expectNoA11yViolations(container);
  });
});
