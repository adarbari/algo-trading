import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FeatureCombobox } from './FeatureCombobox';

const OPTIONS = [
  { value: 'rollup.iv30@v1.iv30', label: 'rollup.iv30@v1.iv30', inputLabel: 'IV30', group: 'iv' },
  { value: 'feature.vol_gap', label: 'feature.vol_gap', group: 'Your features' },
];

describe('FeatureCombobox', () => {
  it('searches the options and reports the picked feature', async () => {
    const onPick = vi.fn();
    const { container } = render(
      <FeatureCombobox aria-label="Feature" options={OPTIONS} onPick={onPick} />,
    );
    await userEvent.type(screen.getByRole('combobox', { name: 'Feature' }), 'gap');
    await userEvent.click(screen.getByRole('option', { name: /feature\.vol_gap/ }));
    expect(onPick).toHaveBeenCalledWith('feature.vol_gap');
    await expectNoA11yViolations(container);
  });

  it('shows the chosen feature by its input label', () => {
    render(
      <FeatureCombobox
        aria-label="Feature"
        options={OPTIONS}
        value="rollup.iv30@v1.iv30"
        onPick={vi.fn()}
      />,
    );
    expect(screen.getByRole('combobox', { name: 'Feature' })).toHaveValue('IV30');
  });

  it('says when the catalogue failed to load', async () => {
    render(<FeatureCombobox aria-label="Feature" options={[]} failed onPick={vi.fn()} />);
    await userEvent.click(screen.getByRole('combobox', { name: 'Feature' }));
    expect(screen.getByText('The feature catalogue failed to load.')).toBeInTheDocument();
  });
});
