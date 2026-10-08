import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { StatusStrip, type StatusIssue } from './StatusStrip';

const ISSUES: StatusIssue[] = [
  { id: 'a', severity: 'failing', title: 'Run failed', detail: 'Screens held back.' },
  { id: 'b', severity: 'warning', title: 'Screener not run', actions: <button>Open</button> },
  { id: 'c', severity: 'warning', title: 'Key missing' },
];

describe('StatusStrip', () => {
  it('shows the pills, the most serious message and the rest as a count', () => {
    render(<StatusStrip issues={ISSUES} />);
    expect(screen.getByText('1 failing')).toBeInTheDocument();
    expect(screen.getByText('2 warnings')).toBeInTheDocument();
    expect(screen.getByText('Run failed')).toBeInTheDocument();
    expect(screen.getByText('and 2 more')).toBeInTheDocument();
    expect(screen.queryByText('Screens held back.')).not.toBeInTheDocument();
  });

  it('expands from the keyboard and lists every issue with its actions', async () => {
    render(<StatusStrip issues={ISSUES} />);
    const bar = screen.getByRole('button', { name: /1 failing/ });
    expect(bar).toHaveAttribute('aria-expanded', 'false');
    bar.focus();
    await userEvent.keyboard('{Enter}');
    expect(bar).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('Screens held back.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument();
    await userEvent.keyboard('{Enter}');
    expect(bar).toHaveAttribute('aria-expanded', 'false');
  });

  it('snoozes one issue by id', async () => {
    const onSnooze = vi.fn();
    render(<StatusStrip issues={ISSUES} onSnooze={onSnooze} defaultExpanded />);
    await userEvent.click(
      screen.getAllByRole('button', { name: 'Snooze 24h' }).at(1) as HTMLElement,
    );
    expect(onSnooze).toHaveBeenCalledWith('b');
  });

  it('offers no snooze without a handler', () => {
    render(<StatusStrip issues={ISSUES} defaultExpanded />);
    expect(screen.queryByRole('button', { name: 'Snooze 24h' })).not.toBeInTheDocument();
  });

  it('renders nothing when clear, or the slim line when asked', () => {
    const { container, rerender } = render(<StatusStrip issues={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<StatusStrip issues={[]} allClear="All systems normal" />);
    expect(screen.getByText('All systems normal')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <StatusStrip issues={ISSUES} onSnooze={vi.fn()} defaultExpanded />,
    );
    await expectNoA11yViolations(container);
  });
});
