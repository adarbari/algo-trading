import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PendingRow } from './PendingRow';

describe('PendingRow', () => {
  it('shows the status label, the name, the summary and the actions', () => {
    render(
      <PendingRow
        label="Waiting on formula"
        help={<button type="button">About waiting</button>}
        name="feature.draft_near_high"
        summary=">= -0.05"
        actions={<button type="button">Skip</button>}
      />,
    );
    expect(
      screen.getByRole('group', { name: 'Waiting on formula: feature.draft_near_high' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Waiting on formula')).toBeInTheDocument();
    expect(screen.getByText('feature.draft_near_high')).toBeInTheDocument();
    expect(screen.getByText('>= -0.05')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About waiting' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip' })).toBeInTheDocument();
  });

  it('leaves out what it is not given', () => {
    render(<PendingRow label="Waiting on formula" name="feature.x" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <PendingRow
        label="Waiting on formula"
        name="feature.draft_near_high"
        summary=">= -0.05"
        actions={<button type="button">Skip</button>}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
