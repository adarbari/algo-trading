import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Sparkline, sparklinePath } from './Sparkline';

describe('Sparkline', () => {
  it('is an image with a generated summary and the up tone when rising', () => {
    const { container } = render(
      <Sparkline label="IV30" values={[0.2, 0.25, 0.22]} format={{ kind: 'percent' }} />,
    );
    expect(
      screen.getByRole('img', { name: 'IV30, 3 values: 20.0% to 22.0%, low 20.0%, high 25.0%' }),
    ).toBeInTheDocument();
    expect(container.querySelector('path')).toHaveAttribute('data-tone', 'up');
  });

  it('uses the down tone when falling, or the given series tone', () => {
    const { container, rerender } = render(<Sparkline label="x" values={[3, 2, 1]} />);
    expect(container.querySelector('path')).toHaveAttribute('data-tone', 'down');
    rerender(<Sparkline label="x" values={[3, 2, 1]} tone="s3" />);
    expect(container.querySelector('path')).toHaveAttribute('data-tone', 's3');
  });

  it('breaks the line at gaps and draws the baseline', () => {
    expect(sparklinePath([1, null, 2, 3], 1, 3)).toMatch(
      /^M0\.00 22\.00M66\.67 12\.00L100\.00 2\.00$/,
    );
    const { container } = render(<Sparkline label="x" values={[99, 101]} baseline={100} />);
    expect(container.querySelector('line')).toBeInTheDocument();
  });

  it('shows loading and no-data states', () => {
    const { rerender } = render(<Sparkline label="IV30" values={[]} loading />);
    expect(screen.getByRole('img', { name: 'IV30: loading' })).toBeInTheDocument();
    rerender(<Sparkline label="IV30" values={[1]} />);
    expect(screen.getByRole('img', { name: 'IV30: no data' })).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Sparkline label="IV30" values={[1, 2, 3]} showLast />);
    await expectNoA11yViolations(container);
  });
});
