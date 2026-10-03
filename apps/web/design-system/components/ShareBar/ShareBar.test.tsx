import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ShareBar } from './ShareBar';

describe('ShareBar', () => {
  it('is a named meter with the percentage as value and text', () => {
    render(<ShareBar value={0.941} label="Coverage" />);
    const meter = screen.getByRole('meter', { name: 'Coverage' });
    expect(meter).toHaveAttribute('aria-valuenow', '94.1');
    expect(meter).toHaveAttribute('aria-valuetext', '94.1%');
    expect(screen.getByText('94.1%')).toBeInTheDocument();
  });

  it('clamps out-of-range values and shows unknown values as a dash', () => {
    const { rerender } = render(<ShareBar value={1.4} label="Over" />);
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '100');
    rerender(<ShareBar value={null} label="Coverage" />);
    expect(screen.getByRole('img')).toHaveAccessibleName('Coverage: unknown');
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ShareBar value={0.5} label="Half" showLabel />);
    await expectNoA11yViolations(container);
  });
});
