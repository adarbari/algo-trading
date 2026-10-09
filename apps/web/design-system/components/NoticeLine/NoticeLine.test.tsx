import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { NoticeLine } from './NoticeLine';

describe('NoticeLine', () => {
  it('is one collapsed line that expands on a click and collapses again', async () => {
    render(
      <NoticeLine label="6 unavailable" summary="No rows for 2026-10-07">
        Full detail
      </NoticeLine>,
    );
    const line = screen.getByRole('button', { name: /6 unavailable/ });
    expect(line).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Full detail')).toBeNull();
    await userEvent.click(line);
    expect(line).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Full detail')).toBeVisible();
    await userEvent.click(line);
    expect(screen.queryByText('Full detail')).toBeNull();
  });

  it('has no accessibility violations, closed or open', async () => {
    const { container } = render(
      <NoticeLine label="2 unavailable" summary="why" defaultOpen>
        Detail
      </NoticeLine>,
    );
    await expectNoA11yViolations(container);
  });
});
