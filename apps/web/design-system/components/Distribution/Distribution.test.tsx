import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Distribution, type DistributionBin } from './Distribution';

const bins: DistributionBin[] = [
  { start: 0, end: 10, count: 4 },
  { start: 10, end: 20, count: 12 },
  { start: 20, end: 40, count: 6 },
];

describe('Distribution', () => {
  it('is an image summarising count, range, the tallest bin and markers', () => {
    render(<Distribution label="ADV" bins={bins} markers={[{ value: 14, label: 'median' }]} />);
    expect(
      screen.getByRole('img', {
        name: 'ADV: 22 values from 0 to 40; most in 10 to 20 (12); median 14.',
      }),
    ).toBeInTheDocument();
  });

  it('draws one bar per bin on a value axis (unequal widths) and labels markers', () => {
    const { container } = render(
      <Distribution
        label="ADV"
        bins={bins}
        markers={[{ value: 30, label: 'AAPL', tone: 'accent' }]}
      />,
    );
    const bars = container.querySelectorAll('rect');
    expect(bars).toHaveLength(3);
    expect(Number(bars[2]?.getAttribute('width'))).toBeGreaterThan(
      Number(bars[1]?.getAttribute('width')),
    );
    expect(screen.getByText('AAPL 30')).toBeInTheDocument();
  });

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<Distribution label="ADV" bins={bins} status="loading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading ADV');
    rerender(<Distribution label="ADV" bins={[]} emptyMessage="Nothing yet" />);
    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
    rerender(<Distribution label="ADV" bins={bins} status="error" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Distribution label="ADV" bins={bins} markers={[{ value: 14, label: 'median' }]} />,
    );
    await expectNoA11yViolations(container);
  });
});
