import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { RegimeLegend } from './RegimeLegend';

describe('RegimeLegend', () => {
  it('explains the shading, the regime, signal and evidence strips once', async () => {
    const { container } = render(<RegimeLegend />);
    expect(screen.getByRole('region', { name: 'How to read the charts' })).toBeVisible();
    const shading = screen.getByRole('list', { name: 'Falls and recoveries' });
    expect(
      within(shading)
        .getAllByRole('listitem')
        .map((i) => i.textContent),
    ).toEqual(['Market fall, peak to trough', 'Recovery, trough to new high']);
    expect(
      within(screen.getByRole('list', { name: 'Recessions' })).getByText('NBER recession'),
    ).toBeVisible();
    expect(
      within(screen.getByRole('list', { name: 'Regime' }))
        .getAllByRole('listitem')
        .map((i) => i.textContent),
    ).toEqual(['Clear', 'Clouds building', 'Storm', 'Severe storm', 'Not computed']);
    expect(
      within(screen.getByRole('list', { name: 'Signal' })).getByText('Signal on'),
    ).toBeVisible();
    expect(
      within(screen.getByRole('list', { name: 'Evidence' })).getAllByRole('listitem'),
    ).toHaveLength(3);
    await expectNoA11yViolations(container);
  });

  it('hatches the recession swatch', () => {
    const { container } = render(<RegimeLegend />);
    expect(container.querySelector('[data-swatch="hatch"]')).not.toBeNull();
  });
});
