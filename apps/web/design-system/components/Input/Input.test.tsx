import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Field } from '../Field';
import { Input } from './Input';

describe('Input', () => {
  it('reports each edit as a string', async () => {
    const onValueChange = vi.fn();
    render(<Input aria-label="Name" onValueChange={onValueChange} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'ab');
    expect(onValueChange).toHaveBeenLastCalledWith('ab');
  });

  it('is labelled, described and marked invalid by its Field', () => {
    render(
      <Field label="Threshold" hint="Percent" error="Must be positive" required>
        <Input defaultValue="-1" />
      </Field>,
    );
    const input = screen.getByRole('textbox', { name: /Threshold/ });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toBeRequired();
    expect(input).toHaveAccessibleDescription('Percent Must be positive');
  });

  it('renders adornments around the text', () => {
    render(<Input aria-label="Price" start="$" end="USD" />);
    expect(screen.getByText('$')).toBeInTheDocument();
    expect(screen.getByText('USD')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Input aria-label="Name" />
        <Field label="Weight" error="Too high">
          <Input defaultValue="200" />
        </Field>
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
