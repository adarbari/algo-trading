import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ExpandableRow } from './ExpandableRow';

describe('ExpandableRow', () => {
  it('reports the requested state from the summary button', async () => {
    const onOpenChange = vi.fn();
    render(
      <ExpandableRow title="vrp_scanner" essential="12" open={false} onOpenChange={onOpenChange}>
        detail
      </ExpandableRow>,
    );
    const button = screen.getByRole('button', { name: 'vrp_scanner 12' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(button);
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('renders the detail only while open', () => {
    const { rerender } = render(
      <ExpandableRow title="a" open={false} onOpenChange={vi.fn()}>
        detail
      </ExpandableRow>,
    );
    expect(screen.queryByText('detail')).not.toBeInTheDocument();
    rerender(
      <ExpandableRow title="a" open onOpenChange={vi.fn()}>
        detail
      </ExpandableRow>,
    );
    expect(screen.getByText('detail')).toBeVisible();
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens with Enter from the keyboard', async () => {
    const onOpenChange = vi.fn();
    render(
      <ExpandableRow title="a" open={false} onOpenChange={onOpenChange}>
        detail
      </ExpandableRow>,
    );
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard('{Enter}');
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ExpandableRow title="vrp_scanner" badge="Preset" essential="12" open onOpenChange={vi.fn()}>
        detail
      </ExpandableRow>,
    );
    await expectNoA11yViolations(container);
  });
});
