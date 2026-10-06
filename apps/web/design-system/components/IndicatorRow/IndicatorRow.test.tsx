import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { IndicatorRow, type IndicatorRowProps } from './IndicatorRow';

const base: IndicatorRowProps = {
  status: { tone: 'warning', label: 'On' },
  name: 'Are banks still lending?',
  technicalName: 'Senior loan officer survey',
  description: 'Net share of banks tightening.',
  value: 21.4,
  format: { kind: 'number', digits: 1 },
  unit: '%',
};

describe('IndicatorRow', () => {
  it('shows the status, names, description and the value with its unit', () => {
    render(<IndicatorRow {...base} />);
    expect(screen.getByText('On')).toBeInTheDocument();
    expect(screen.getByText('Are banks still lending?')).toBeInTheDocument();
    expect(screen.getByText('Senior loan officer survey')).toBeInTheDocument();
    expect(screen.getByText('Net share of banks tightening.')).toBeInTheDocument();
    expect(screen.getByText(/21\.4/)).toHaveTextContent('21.4 %');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows a missing value as a dash without its unit', () => {
    render(<IndicatorRow {...base} value={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('%')).toBeNull();
  });

  it('says what changed in words for screen readers', () => {
    const { rerender } = render(<IndicatorRow {...base} changed="up" />);
    expect(screen.getByText(/Increased/)).toBeInTheDocument();
    rerender(<IndicatorRow {...base} changed="down" changedLabel="Turned off this week" />);
    expect(screen.getByText(/Turned off this week/)).toBeInTheDocument();
    rerender(<IndicatorRow {...base} changed="new" />);
    expect(screen.getByText(/New/)).toBeInTheDocument();
  });

  it('reads a dot indicator as its state in words', () => {
    render(<IndicatorRow {...base} indicator="dot" />);
    expect(screen.getByText(/On:/)).toBeInTheDocument();
  });

  it('expands from the header button with the keyboard and reports the state', async () => {
    const onOpenChange = vi.fn();
    render(
      <IndicatorRow {...base} changed="up" onOpenChange={onOpenChange}>
        Why it matters.
      </IndicatorRow>,
    );
    const button = screen.getByRole('button', { name: /Are banks still lending\?/ });
    expect(button).toHaveAccessibleName(expect.stringContaining('Increased'));
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Why it matters.')).not.toBeVisible();
    const user = userEvent.setup();
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Why it matters.')).toBeVisible();
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it('announces loading', () => {
    render(<IndicatorRow {...base} loading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading Are banks still lending?');
  });

  it('has no accessibility violations, collapsed, open and flat', async () => {
    const { container, rerender } = render(
      <IndicatorRow {...base} changed="new">
        Detail
      </IndicatorRow>,
    );
    await expectNoA11yViolations(container);
    rerender(
      <IndicatorRow {...base} indicator="dot" defaultOpen>
        Detail
      </IndicatorRow>,
    );
    await expectNoA11yViolations(container);
    rerender(<IndicatorRow {...base} />);
    await expectNoA11yViolations(container);
  });
});
