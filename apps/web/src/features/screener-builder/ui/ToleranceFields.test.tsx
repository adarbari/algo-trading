import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ToleranceFields } from './ToleranceFields';

const FEATURE = { name: 'f', dtype: 'float32', unit: 'decimal' } as CatalogueFeature;
const SOFT: Criterion = {
  id: 'a',
  field: 'f',
  op: 'gte',
  mode: 'soft',
  value: 0.1,
  tolerance: 0.02,
};

describe('ToleranceFields', () => {
  it('shows the tolerance in the field unit and stores it as given', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <ToleranceFields criterion={SOFT} feature={FEATURE} onChange={onChange} />,
    );
    const input = screen.getByRole('spinbutton', { name: 'Tolerance' });
    expect(input).toHaveValue('2.0');
    await userEvent.clear(input);
    await userEvent.type(input, '3{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ ...SOFT, tolerance: 0.03 });
    await expectNoA11yViolations(container);
  });

  it('switches to a share of the threshold and picks the near-miss decision', async () => {
    const onChange = vi.fn();
    render(<ToleranceFields criterion={SOFT} feature={FEATURE} onChange={onChange} />);
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Tolerance unit' }),
      'relative',
    );
    expect(onChange).toHaveBeenLastCalledWith({ ...SOFT, tolerance: { relative: 0.1 } });
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Decision for a near miss' }),
      'liquidity risk',
    );
    expect(onChange).toHaveBeenLastCalledWith({ ...SOFT, on_miss: 'LIQUIDITY_RISK' });
  });

  it('offers no near-miss decision for a score criterion and clears an empty tolerance', async () => {
    const onChange = vi.fn();
    render(
      <ToleranceFields
        criterion={{ ...SOFT, mode: 'score' }}
        feature={FEATURE}
        onChange={onChange}
      />,
    );
    expect(screen.queryByRole('combobox', { name: 'Decision for a near miss' })).toBeNull();
    await userEvent.clear(screen.getByRole('spinbutton', { name: 'Tolerance' }));
    await userEvent.tab();
    expect(onChange).toHaveBeenLastCalledWith({ ...SOFT, mode: 'score', tolerance: undefined });
  });
});
