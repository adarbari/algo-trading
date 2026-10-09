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

  it('shows the chosen option by its inputLabel, with the full label as a tooltip', () => {
    render(
      <Combobox
        aria-label="Feature"
        mono
        value="rollup.price_stats@v2.close"
        options={[
          {
            value: 'rollup.price_stats@v2.close',
            label: 'rollup.price_stats@v2.close',
            inputLabel: 'Last close',
          },
        ]}
      />,
    );
    const input = screen.getByRole('combobox', { name: 'Feature' });
    expect(input).toHaveValue('Last close');
    expect(input.closest('[title]')).toHaveAttribute('title', 'rollup.price_stats@v2.close');
  });

  describe('search', () => {
    const PEOPLE = [
      { value: 'NVDA', label: 'NVDA', description: 'NVIDIA Corp' },
      { value: 'NVO', label: 'NVO', description: 'Novo Nordisk' },
    ];

    it('lists only once something is typed, adds on Enter and clears', async () => {
      const onValueChange = vi.fn();
      render(<Combobox search aria-label="Add" options={PEOPLE} onValueChange={onValueChange} />);
      const input = screen.getByRole('combobox', { name: 'Add' });
      await userEvent.click(input);
      expect(screen.queryByRole('listbox')).toBeNull();
      await userEvent.type(input, 'nv');
      expect(screen.getAllByRole('option')).toHaveLength(2);
      await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}');
      expect(onValueChange).toHaveBeenCalledWith('NVO', PEOPLE[1]);
      expect(input).toHaveValue('');
      await userEvent.type(input, 'nv{ArrowDown}{Enter}');
      expect(onValueChange).toHaveBeenLastCalledWith('NVDA', PEOPLE[0]);
    });

    it('Escape closes the list and leaves the box', async () => {
      render(<Combobox search aria-label="Add" options={PEOPLE} />);
      const input = screen.getByRole('combobox');
      await userEvent.type(input, 'nv');
      await userEvent.keyboard('{Escape}');
      expect(screen.queryByRole('listbox')).toBeNull();
      expect(input).not.toHaveFocus();
    });

    it('focuses on its key from outside a text field, not from inside one', async () => {
      render(
        <>
          <input aria-label="Other" />
          <Combobox search focusKey="/" aria-label="Add" options={PEOPLE} />
        </>,
      );
      const box = screen.getByRole('combobox', { name: 'Add' });
      await userEvent.keyboard('/');
      expect(box).toHaveFocus();
      await userEvent.click(screen.getByLabelText('Other'));
      await userEvent.keyboard('/');
      expect(screen.getByLabelText('Other')).toHaveFocus();
    });

    it('has no accessibility violations, open', async () => {
      const { container } = render(
        <Combobox search focusKey="/" aria-label="Add" options={PEOPLE} />,
      );
      await userEvent.type(screen.getByRole('combobox'), 'nv');
      await expectNoA11yViolations(container);
    });
  });
});
