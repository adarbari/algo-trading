import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Input } from '../Input';
import { Field } from './Field';

describe('Field', () => {
  it('names its control with the label', () => {
    render(
      <Field label="Universe">
        <Input />
      </Field>,
    );
    expect(screen.getByRole('textbox', { name: 'Universe' })).toBeInTheDocument();
  });

  it('describes the control with hint then error and marks it invalid', () => {
    render(
      <Field label="Weight" hint="0 to 100" error="Too high">
        <Input defaultValue="200" />
      </Field>,
    );
    const input = screen.getByRole('textbox', { name: 'Weight' });
    expect(input).toHaveAccessibleDescription('0 to 100 Too high');
    expect(input).toBeInvalid();
  });

  it('keeps a hidden label for screen readers and disables the control', () => {
    render(
      <Field label="Filter tickers" hideLabel disabled>
        <Input />
      </Field>,
    );
    expect(screen.getByRole('textbox', { name: 'Filter tickers' })).toBeDisabled();
  });

  it('uses a caller-supplied id', () => {
    render(
      <Field label="Name" id="screener-name">
        <Input />
      </Field>,
    );
    expect(screen.getByRole('textbox')).toHaveAttribute('id', 'screener-name');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Field label="Name" hint="Unique" error="Taken" required layout="inline">
        <Input />
      </Field>,
    );
    await expectNoA11yViolations(container);
  });
});
