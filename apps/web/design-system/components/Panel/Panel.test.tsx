import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Panel } from './Panel';

describe('Panel', () => {
  it('is a region named by its heading, with actions, body and footer', () => {
    render(
      <Panel title="Criteria" actions={<button type="button">Add</button>} footer="Note">
        Body
      </Panel>,
    );
    const region = screen.getByRole('region', { name: 'Criteria' });
    expect(region).toContainElement(screen.getByRole('heading', { level: 2, name: 'Criteria' }));
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(screen.getByText('Note')).toBeInTheDocument();
  });

  it('is busy while loading and hides its content', () => {
    render(
      <Panel title="Ideas" state="loading">
        Body
      </Panel>,
    );
    expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(screen.queryByText('Body')).toBeNull();
  });

  it('shows the empty message', () => {
    render(<Panel title="Ideas" state="empty" emptyMessage="No ideas today" />);
    expect(screen.getByText('No ideas today')).toBeInTheDocument();
  });

  it('shows the error with a working Retry', async () => {
    const onRetry = vi.fn();
    render(<Panel title="Runs" state="error" errorMessage="Failed" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Panel title="One" description="context">
          Body
        </Panel>
        <Panel title="Two" state="error" onRetry={vi.fn()} headingLevel={3} />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
