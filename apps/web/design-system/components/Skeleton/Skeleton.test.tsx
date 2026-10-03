import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Skeleton } from './Skeleton';

describe('Skeleton', () => {
  it('announces one busy status with its label; the shapes are hidden', () => {
    const { container } = render(<Skeleton lines={4} label="Loading ideas…" />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveTextContent('Loading ideas…');
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(4);
  });

  it('draws a block or table rows', () => {
    const { container, rerender } = render(<Skeleton variant="rect" height="lg" />);
    expect(container.querySelector('[data-height="lg"]')).toBeInTheDocument();
    rerender(<Skeleton variant="table" rows={2} columns={3} />);
    const rows = container.querySelectorAll('[data-variant="table"] > [aria-hidden="true"]');
    expect(rows).toHaveLength(2);
    expect(rows[0]?.children).toHaveLength(3);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Skeleton variant="table" />);
    await expectNoA11yViolations(container);
  });
});
