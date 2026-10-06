import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { RunRegimeChip } from './RunRegimeChip';

describe('RunRegimeChip', () => {
  it('shows the label the run stamped, in its tone', async () => {
    const { container } = render(<RunRegimeChip label="STRESS" />);
    expect(screen.getByText('Regime: Storm')).toHaveAttribute('data-tone', 'negative');
    await expectNoA11yViolations(container);
  });

  it('says so, muted, when the run stamped none or something else', () => {
    const { rerender } = render(<RunRegimeChip label={null} />);
    expect(screen.getByText('Regime: not recorded for this run')).toHaveAttribute(
      'data-tone',
      'neutral',
    );
    rerender(<RunRegimeChip label="SUNNY" />);
    expect(screen.getByText('Regime: not recorded for this run')).toBeVisible();
  });
});
