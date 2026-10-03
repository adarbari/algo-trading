import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { StatStrip } from './StatStrip';

describe('StatStrip', () => {
  it('renders a labelled region of label / value / sub groups', () => {
    render(
      <StatStrip
        label="Summary"
        items={[
          {
            label: 'Completeness',
            value: 0.964,
            format: { kind: 'percent' },
            sub: 'of expected rows',
          },
          { label: 'Open issues', value: 3, tone: 'warning' },
        ]}
      />,
    );
    expect(screen.getByRole('region', { name: 'Summary' })).toBeInTheDocument();
    expect(screen.getByText('96.4%').tagName).toBe('DD');
    expect(screen.getByText('3')).toHaveAttribute('data-tone', 'warning');
    expect(screen.getByText('of expected rows')).toBeInTheDocument();
  });

  it('formats deltas with their tone unless a tone is given', () => {
    render(
      <StatStrip
        label="Moves"
        items={[{ label: 'Day', value: -0.01, format: { kind: 'delta' } }]}
      />,
    );
    expect(screen.getByText('−1.00%')).toHaveAttribute('data-tone', 'down');
  });

  it('shows loading placeholders, the empty message and errors as an alert', () => {
    const { rerender } = render(
      <StatStrip label="S" loading items={[{ label: 'Run', value: '1h' }]} />,
    );
    expect(screen.getByRole('region')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('1h')).toBeNull();
    rerender(<StatStrip label="S" items={[]} emptyMessage="No run yet" />);
    expect(screen.getByText('No run yet')).toBeInTheDocument();
    rerender(<StatStrip label="S" items={[]} error="Failed to load" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <StatStrip
        label="Summary"
        items={[{ label: 'Run', value: '1h 21m', sub: 'alert at 2h 30m' }]}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
