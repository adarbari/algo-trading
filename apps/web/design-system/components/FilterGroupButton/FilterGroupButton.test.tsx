import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { FilterGroupButton } from './FilterGroupButton';

describe('FilterGroupButton', () => {
  it('opens a dialog named by the label, and focus returns to the button on Escape', async () => {
    const { container } = render(
      <FilterGroupButton label="Setup">
        <button type="button">Inside</button>
      </FilterGroupButton>,
    );
    const button = screen.getByRole('button', { name: 'Setup' });
    expect(button).toHaveAttribute('aria-haspopup', 'dialog');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog', { name: 'Setup' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(button).toHaveFocus();
    await expectNoA11yViolations(container);
  });

  it('shows the count and the active state only while the group holds filters', () => {
    const { rerender, container } = render(
      <FilterGroupButton label="Setup" activeCount={2}>
        x
      </FilterGroupButton>,
    );
    expect(screen.getByRole('button', { name: 'Setup, 2 active' })).toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute('data-active', 'true');
    rerender(
      <FilterGroupButton label="Setup" activeCount={0}>
        x
      </FilterGroupButton>,
    );
    expect(screen.getByRole('button', { name: 'Setup' })).toBeInTheDocument();
    expect(container.firstElementChild).not.toHaveAttribute('data-active');
  });
});
