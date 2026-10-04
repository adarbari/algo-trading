import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { TieBreakField } from './TieBreakField';

const CATALOGUE = [
  {
    name: 'feature.iv_hv_spread',
    dtype: 'float32',
    description: 'IV minus HV',
    unit: 'ratio',
    scope: 'site',
  },
  { name: 'instrument.sector', dtype: 'str', description: 'Sector', unit: null, scope: 'site' },
] as CatalogueFeature[];

describe('TieBreakField', () => {
  it('offers numeric features only and changes the order', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <TieBreakField
        catalogue={CATALOGUE}
        field="feature.iv_hv_spread"
        order="desc"
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Low first' }));
    expect(onChange).toHaveBeenCalledWith('feature.iv_hv_spread', 'asc');
    await userEvent.click(screen.getByRole('combobox', { name: 'Feature or formula' }));
    expect(screen.queryByRole('option', { name: /instrument\.sector/ })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('clears the column (one a preset sets can be cleared in a copy)', async () => {
    const onChange = vi.fn();
    render(
      <TieBreakField
        catalogue={CATALOGUE}
        field="feature.iv_hv_spread"
        order="asc"
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Clear tie-break' }));
    expect(onChange).toHaveBeenCalledWith(null, 'asc');
  });

  it('has nothing to clear until a column is chosen', () => {
    render(<TieBreakField catalogue={CATALOGUE} field={null} order="desc" onChange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Clear tie-break' })).toBeNull();
  });

  it('cannot order until a column is chosen', () => {
    render(<TieBreakField catalogue={CATALOGUE} field={null} order="desc" onChange={vi.fn()} />);
    expect(screen.getByRole('radio', { name: 'Low first' })).toBeDisabled();
  });
});
