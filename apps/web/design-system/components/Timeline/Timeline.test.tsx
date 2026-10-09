import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Timeline, timelineDomain, type TimelineRow } from './Timeline';

const ROWS: TimelineRow[] = [
  {
    id: 'a',
    label: 'Credit spreads',
    spans: [{ id: 's', from: -40, to: 25, tone: 's2', label: 'On' }],
    markers: [{ id: 'm', at: -40, tone: 's2', label: 'Flagged' }],
  },
  { id: 'b', label: 'Sahm rule', note: 'Never fired' },
  {
    id: 'c',
    label: 'Trend break',
    spans: [{ id: 's', from: -5, to: null, tone: 's1', label: 'On' }],
  },
];

describe('Timeline', () => {
  it('lists each row with its note and says its marks in text', () => {
    render(<Timeline rows={ROWS} label="Signals" reference={{ at: 0, label: 'the peak' }} />);
    const list = screen.getByRole('list', { name: 'Signals' });
    expect(list.querySelectorAll('li')).toHaveLength(3);
    expect(screen.getByText('Never fired')).toBeInTheDocument();
    expect(screen.getByText(/^On .40 to 25; Flagged .40$/)).toBeInTheDocument();
    expect(screen.getByText(/^On .5 to still on$/)).toBeInTheDocument();
    expect(screen.getByText('Line: the peak')).toBeInTheDocument();
  });

  it('shows the empty message and the error', () => {
    const { rerender } = render(<Timeline rows={[]} label="Signals" emptyMessage="None stored" />);
    expect(screen.getByText('None stored')).toBeInTheDocument();
    rerender(<Timeline rows={ROWS} label="Signals" error="Failed" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Failed');
  });

  it('is busy while loading', () => {
    render(<Timeline rows={ROWS} label="Signals" loading />);
    expect(screen.getByText('Signals: loading')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('shares one domain across rows, rounded outward, and includes the reference', () => {
    expect(timelineDomain([ROWS], 0)).toEqual({ min: -40, max: 40 });
    expect(timelineDomain([], undefined)).toEqual({ min: -10, max: 10 });
    expect(
      timelineDomain([
        [{ id: 'x', label: 'x', markers: [{ id: 'm', at: 3, tone: 's1', label: 'a' }] }],
      ]),
    ).toEqual({
      min: 2,
      max: 4,
    });
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Timeline
        rows={ROWS}
        label="Signals"
        reference={{ at: 0, label: 'the peak' }}
        axisLabel="Days"
      />,
    );
    await expectNoA11yViolations(container);
  });
});
