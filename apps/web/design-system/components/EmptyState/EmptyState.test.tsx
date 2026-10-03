import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('shows the title, description and action', () => {
    render(
      <EmptyState
        title="No ideas"
        description="Loosen a criterion"
        action={<button type="button">Edit</button>}
      />,
    );
    expect(screen.getByText('No ideas')).toBeInTheDocument();
    expect(screen.getByText('Loosen a criterion')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('can be bordered and compact', () => {
    const { container } = render(<EmptyState title="x" bordered compact />);
    expect(container.firstElementChild).toHaveAttribute('data-bordered', 'true');
    expect(container.firstElementChild).toHaveAttribute('data-compact', 'true');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<EmptyState title="No ideas" icon="search" />);
    await expectNoA11yViolations(container);
  });
});
