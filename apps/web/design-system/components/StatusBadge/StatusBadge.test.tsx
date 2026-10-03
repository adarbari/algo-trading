import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('shows its state in words with the tone as a styling hook', () => {
    render(<StatusBadge tone="warning">EVENT_RISK</StatusBadge>);
    expect(screen.getByText('EVENT_RISK')).toHaveAttribute('data-tone', 'warning');
  });

  it('is neutral by default and keeps icons decorative', () => {
    const { container } = render(<StatusBadge icon="check">PASS</StatusBadge>);
    expect(screen.getByText('PASS')).toHaveAttribute('data-tone', 'neutral');
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <StatusBadge tone="positive">PASS</StatusBadge>
        <StatusBadge tone="accent" title="Soft criteria missed">
          WATCH
        </StatusBadge>
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
