import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FeaturePicker, featureOptions } from './FeaturePicker';

const CATALOGUE = [
  {
    name: 'rollup.iv30@v1.iv30',
    description: 'Our 30-day IV',
    unit: 'decimal',
    group: 'iv30@v1',
    scope: 'site',
    licence: 'personal',
  },
  {
    name: 'feature.vol_gap',
    description: 'IV minus HV',
    unit: 'ratio',
    group: null,
    scope: 'user',
    licence: 'open',
  },
] as CatalogueFeature[];

describe('featureOptions', () => {
  it("describes a field by its guide's one-line summary when it has one", () => {
    const guided = {
      ...CATALOGUE[0],
      guide: { summary: 'The 30-day at-the-money implied volatility.' },
    } as CatalogueFeature;
    expect(featureOptions([guided])[0]?.description).toBe(
      'The 30-day at-the-money implied volatility. · fraction (shown as %) · personal licence',
    );
  });

  it('describes each feature with its unit and licence, and badges formulas', () => {
    const [iv, own] = featureOptions(CATALOGUE);
    expect(iv).toMatchObject({ value: 'rollup.iv30@v1.iv30', group: 'iv30@v1' });
    expect(iv?.description).toBe('Our 30-day IV · fraction (shown as %) · personal licence');
    expect(own).toMatchObject({ badge: 'yours', group: 'Your features' });
  });
});

describe('FeaturePicker', () => {
  it('searches the catalogue and reports the chosen field', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <FeaturePicker catalogue={CATALOGUE} value={null} onChange={onChange} />,
    );
    await userEvent.type(screen.getByRole('combobox', { name: 'Feature or formula' }), 'gap');
    await userEvent.click(screen.getByRole('option', { name: /feature\.vol_gap/ }));
    expect(onChange).toHaveBeenCalledWith('feature.vol_gap');
    await expectNoA11yViolations(container);
  });

  it('shows the chosen feature by its readable name, the full id as the tooltip', () => {
    render(<FeaturePicker catalogue={CATALOGUE} value="rollup.iv30@v1.iv30" onChange={vi.fn()} />);
    const input = screen.getByRole('combobox', { name: 'Feature or formula' });
    expect(input).toHaveValue('IV30');
    expect(input.closest('[title]')).toHaveAttribute('title', 'rollup.iv30@v1.iv30');
  });
});
