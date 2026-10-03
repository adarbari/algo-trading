import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { StackedBar } from './StackedBar';

const segments = [
  { id: 'ok', label: 'OK', value: 3, tone: 'positive' as const },
  { id: 'stale', label: 'Stale', value: 1, tone: 'warning' as const },
  { id: 'err', label: 'Errors', value: 0, tone: 'negative' as const },
];

describe('StackedBar', () => {
  it('names the bar with every segment, its count and share', () => {
    render(<StackedBar label="Chains" segments={segments} />);
    expect(screen.getByRole('img')).toHaveAccessibleName(
      'Chains: OK 3 (75.0%), Stale 1 (25.0%), Errors 0 (0.0%)',
    );
  });

  it('draws only non-empty segments but lists all of them in the legend', () => {
    const { container } = render(<StackedBar label="Chains" segments={segments} />);
    expect(container.querySelectorAll('[role="img"] > [data-tone]')).toHaveLength(2);
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });

  it('shows the empty message, loading and errors', () => {
    const { rerender } = render(<StackedBar label="Chains" segments={[]} emptyMessage="Nothing" />);
    expect(screen.getByText('Nothing')).toBeInTheDocument();
    rerender(<StackedBar label="Chains" segments={segments} loading />);
    expect(screen.getByRole('img')).toHaveAccessibleName('Chains: loading');
    rerender(<StackedBar label="Chains" segments={segments} error="Failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<StackedBar label="Chains" segments={segments} />);
    await expectNoA11yViolations(container);
  });
});
