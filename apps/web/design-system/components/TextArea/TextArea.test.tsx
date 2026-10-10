import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Field } from '../Field';
import { TextArea } from './TextArea';

describe('TextArea', () => {
  it('reports each edit as a string', async () => {
    const onValueChange = vi.fn();
    render(<TextArea aria-label="Thesis" onValueChange={onValueChange} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Thesis' }), 'a\nb');
    expect(onValueChange).toHaveBeenLastCalledWith('a\nb');
  });

  it('is labelled, described and marked invalid by its Field', () => {
    render(
      <Field label="Mechanism" hint="Who is forced" error="Required" required>
        <TextArea defaultValue="" />
      </Field>,
    );
    const box = screen.getByRole('textbox', { name: /Mechanism/ });
    expect(box).toHaveAttribute('aria-invalid', 'true');
    expect(box).toBeRequired();
    expect(box).toHaveAccessibleDescription('Who is forced Required');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Field label="Notes" hint="Optional">
        <TextArea />
      </Field>,
    );
    await expectNoA11yViolations(container);
  });
});
