import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Field } from '../Field';
import { Combobox, type ComboboxOption } from './Combobox';

const OPTIONS: ComboboxOption[] = [
  { value: 'iv30', label: 'iv30', description: 'Implied volatility', group: 'Catalogue' },
  { value: 'close', label: 'close', description: 'Last close', group: 'Catalogue' },
  { value: 'spread', label: 'iv_hv_spread', badge: 'formula', group: 'Formulas' },
  { value: 'off', label: 'disabled_one', disabled: true, group: 'Formulas' },
];

describe('Combobox', () => {
  it('opens on ArrowDown, moves with arrows, skips disabled options and selects on Enter', async () => {
    const onValueChange = vi.fn();
    render(<Combobox aria-label="Feature" options={OPTIONS} onValueChange={onValueChange} />);
    const input = screen.getByRole('combobox', { name: 'Feature' });
    expect(input).toHaveAttribute('aria-expanded', 'false');
    input.focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(input).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('listbox', { name: 'Feature' })).toBeInTheDocument();
    const active = () => document.getElementById(input.getAttribute('aria-activedescendant') ?? '');
    expect(active()).toHaveTextContent('iv30');
    await userEvent.keyboard('{ArrowUp}');
    expect(active()).toHaveTextContent('iv_hv_spread');
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}');
    expect(onValueChange).toHaveBeenCalledWith('close', OPTIONS[1]);
    expect(input).toHaveValue('close');
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });

  it('filters by description and badge as the user types', async () => {
    const onInputChange = vi.fn();
    render(<Combobox aria-label="Feature" options={OPTIONS} onInputChange={onInputChange} />);
    await userEvent.type(screen.getByRole('combobox'), 'formula');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option')).toHaveTextContent('iv_hv_spread');
    expect(onInputChange).toHaveBeenLastCalledWith('formula');
  });

  it('groups options under named groups and marks the selection', async () => {
    render(<Combobox aria-label="Feature" options={OPTIONS} defaultValue="close" />);
    await userEvent.click(screen.getByRole('combobox'));
    expect(screen.getByRole('group', { name: 'Formulas' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /close/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('selects by click and closes on Escape', async () => {
    render(<Combobox aria-label="Feature" options={OPTIONS} />);
    const input = screen.getByRole('combobox');
    await userEvent.click(input);
    await userEvent.click(screen.getByRole('option', { name: /iv_hv_spread/ }));
    expect(input).toHaveValue('iv_hv_spread');
    await userEvent.click(input);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('announces loading, empty and error states', async () => {
    const { rerender } = render(
      <Combobox aria-label="Feature" options={[]} loading filter="none" />,
    );
    await userEvent.click(screen.getByRole('combobox'));
    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
    rerender(<Combobox aria-label="Feature" options={[]} filter="none" />);
    expect(screen.getByRole('status')).toHaveTextContent('No matches');
    rerender(<Combobox aria-label="Feature" options={[]} error="Catalogue failed" />);
    expect(screen.getByRole('status')).toHaveTextContent('Catalogue failed');
  });

  it('is labelled by its Field, and the list too', async () => {
    render(
      <Field label="Feature">
        <Combobox options={OPTIONS} />
      </Field>,
    );
    await userEvent.click(screen.getByRole('combobox', { name: 'Feature' }));
    expect(screen.getByRole('listbox', { name: 'Feature' })).toBeInTheDocument();
  });

  it('has no accessibility violations, open', async () => {
    const { container } = render(
      <Combobox aria-label="Feature" options={OPTIONS} defaultValue="iv30" />,
    );
    await userEvent.click(screen.getByRole('combobox'));
    await expectNoA11yViolations(container);
  });
});
