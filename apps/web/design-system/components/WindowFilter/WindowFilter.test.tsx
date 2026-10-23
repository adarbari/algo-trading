import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { WindowFilter } from './WindowFilter';

const UNITS = [
  { value: 'days', label: 'Days' },
  { value: 'sessions', label: 'Sessions' },
];

function setup(onChange = vi.fn()) {
  const view = render(
    <WindowFilter
      value={{ amount: 5, unit: 'days' }}
      onChange={onChange}
      units={UNITS}
      label="Within"
      unitLabel="Unit"
    />,
  );
  return { ...view, onChange };
}

describe('WindowFilter', () => {
  it('reports a new number with the unit kept', async () => {
    const { onChange } = setup();
    const input = screen.getByRole('spinbutton', { name: 'Within' });
    await userEvent.clear(input);
    await userEvent.type(input, '10{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ amount: 10, unit: 'days' });
  });

  it('reports a new unit with the number kept', async () => {
    const { onChange } = setup();
    await userEvent.click(screen.getByRole('radio', { name: 'Sessions' }));
    expect(onChange).toHaveBeenCalledWith({ amount: 5, unit: 'sessions' });
  });

  it('has no accessibility violations', async () => {
    const { container } = setup();
    await expectNoA11yViolations(container);
  });
});
