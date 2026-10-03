import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Field } from '../Field';
import { Select } from './Select';

const OPTIONS = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta', group: 'Later' },
  { value: 'c', label: 'Gamma', group: 'Later' },
];

describe('Select', () => {
  it('reports the chosen value', async () => {
    const onValueChange = vi.fn();
    render(<Select aria-label="Pick" options={OPTIONS} onValueChange={onValueChange} />);
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Pick' }), 'c');
    expect(onValueChange).toHaveBeenCalledWith('c');
  });

  it('starts on the placeholder and groups options', () => {
    render(<Select aria-label="Pick" options={OPTIONS} placeholder="Choose" />);
    expect(screen.getByRole('combobox')).toHaveDisplayValue('Choose');
    expect(screen.getByRole('group', { name: 'Later' })).toBeInTheDocument();
  });

  it('is labelled and marked invalid by its Field', () => {
    render(
      <Field label="Expiry" error="No quotes">
        <Select options={OPTIONS} />
      </Field>,
    );
    const select = screen.getByRole('combobox', { name: 'Expiry' });
    expect(select).toBeInvalid();
    expect(select).toHaveAccessibleDescription('No quotes');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Select aria-label="Pick" options={OPTIONS} />);
    await expectNoA11yViolations(container);
  });
});
