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

  it('draws the highlighted part of each bin over the bar and says how many in the summary', () => {
    const lit = bins.map((b, i) =>
      i === 0 ? { ...b, highlighted: 4 } : { ...b, highlighted: i === 1 ? 5 : 0 },
    );
    const { container } = render(
      <Distribution label="ADV" bins={lit} highlightLabel="pass a squeeze" />,
    );
    expect(container.querySelectorAll('rect')).toHaveLength(5); // 3 bars + 2 highlighted parts
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('9 pass a squeeze');
    expect(container.firstElementChild).toHaveAttribute('data-highlight');
  });

  it('is plain without highlights', () => {
    const { container } = render(<Distribution label="ADV" bins={bins} highlightLabel="pass" />);
    expect(container.querySelectorAll('rect')).toHaveLength(3);
    expect(container.firstElementChild).not.toHaveAttribute('data-highlight');
    expect(screen.getByRole('img').getAttribute('aria-label')).not.toContain('pass');
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

  it('drops quantile labels that would collide but keeps the highlighted one and the summary', () => {
    const markers = [
      { value: 14, label: 'p10' },
      { value: 14.5, label: 'p25' },
      { value: 15, label: 'median' },
      { value: 15.5, label: 'p75' },
      { value: 16, label: 'p90' },
      { value: 15, label: 'AAPL', tone: 'accent' as const },
    ];
    const { container } = render(<Distribution label="ADV" bins={bins} markers={markers} />);
    expect(screen.getByText('AAPL 15')).toBeInTheDocument();
    expect(screen.getByText('p10 14')).toBeInTheDocument();
    expect(screen.queryByText('median 15')).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-tone="default"]')).toHaveLength(5);
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(/p90 16/);
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
