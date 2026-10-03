import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { NumberInput } from './NumberInput';

describe('NumberInput', () => {
  it('is a spinbutton with its value, bounds and unit', () => {
    render(<NumberInput aria-label="IV floor" defaultValue={50} min={0} max={300} suffix="%" />);
    const input = screen.getByRole('spinbutton', { name: 'IV floor' });
    expect(input).toHaveValue('50');
    expect(input).toHaveAttribute('aria-valuenow', '50');
    expect(input).toHaveAttribute('aria-valuemax', '300');
    expect(input).toHaveAttribute('aria-valuetext', '50 %');
    expect(screen.getByText('%')).toBeInTheDocument();
  });

  it('steps with arrow keys (Shift ×10) and clamps', async () => {
    const onValueChange = vi.fn();
    render(
      <NumberInput
        aria-label="Weight"
        defaultValue={95}
        min={0}
        max={100}
        onValueChange={onValueChange}
      />,
    );
    const input = screen.getByRole('spinbutton');
    input.focus();
    await userEvent.keyboard('{ArrowUp}');
    expect(input).toHaveValue('96');
    await userEvent.keyboard('{Shift>}{ArrowUp}{/Shift}');
    expect(input).toHaveValue('100');
    expect(onValueChange).toHaveBeenLastCalledWith(100);
  });

  it('commits typed text on blur, parsing separators, and keeps empty as null', async () => {
    const onValueChange = vi.fn();
    render(<NumberInput aria-label="ADV" step={0.01} onValueChange={onValueChange} />);
    const input = screen.getByRole('spinbutton');
    await userEvent.type(input, '1,234.5');
    await userEvent.tab();
    expect(onValueChange).toHaveBeenLastCalledWith(1234.5);
    expect(input).toHaveValue('1234.50');
    await userEvent.clear(input);
    await userEvent.tab();
    expect(onValueChange).toHaveBeenLastCalledWith(null);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<NumberInput aria-label="Price" prefix="$" defaultValue={5} />);
    await expectNoA11yViolations(container);
  });
});
