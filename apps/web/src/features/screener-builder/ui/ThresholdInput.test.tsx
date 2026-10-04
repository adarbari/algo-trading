import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ThresholdInput } from './ThresholdInput';

const feature = (patch: Partial<CatalogueFeature>): CatalogueFeature =>
  ({ name: 'f', dtype: 'float32', unit: null, categories: [], ...patch }) as CatalogueFeature;

describe('ThresholdInput', () => {
  it('types a fraction as a percent and stores the fraction', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <ThresholdInput
        feature={feature({ unit: 'decimal' })}
        op="gte"
        value={0.5}
        onChange={onChange}
      />,
    );
    const input = screen.getByRole('spinbutton', { name: 'Threshold' });
    expect(input).toHaveValue('50.0');
    await userEvent.clear(input);
    await userEvent.type(input, '7{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(0.07);
    await expectNoA11yViolations(container);
  });

  it('shows two numbers for a range and reports the pair once both are set', async () => {
    const onChange = vi.fn();
    render(
      <ThresholdInput feature={feature({})} op="between" value={[1, 2]} onChange={onChange} />,
    );
    const to = screen.getByRole('spinbutton', { name: 'To' });
    await userEvent.clear(to);
    await userEvent.type(to, '5{Enter}');
    expect(onChange).toHaveBeenLastCalledWith([1, 5]);
  });

  it('takes a list as text and commits it on blur', async () => {
    const onChange = vi.fn();
    render(
      <ThresholdInput
        feature={feature({ dtype: 'str' })}
        op="in"
        value={['HIGH']}
        onChange={onChange}
      />,
    );
    const input = screen.getByRole('textbox', { name: 'Values, separated by commas' });
    await userEvent.clear(input);
    await userEvent.type(input, 'HIGH, LOW,');
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.tab();
    expect(onChange).toHaveBeenCalledWith(['HIGH', 'LOW']);
  });

  it('offers Yes / No for a flag, the categories for a label and nothing for "is empty"', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ThresholdInput
        feature={feature({ dtype: 'bool' })}
        op="eq"
        value={true}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Threshold' }), 'No');
    expect(onChange).toHaveBeenCalledWith(false);
    rerender(
      <ThresholdInput
        feature={feature({ dtype: 'str', categories: ['A', 'B'] })}
        op="eq"
        value="A"
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Threshold' }), 'B');
    expect(onChange).toHaveBeenLastCalledWith('B');
    rerender(
      <ThresholdInput feature={feature({})} op="is_null" value={undefined} onChange={onChange} />,
    );
    expect(screen.getByText('no threshold')).toBeInTheDocument();
  });

  it('lists a text field\'s categories as checkboxes for "in", keeping the field\'s order', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ThresholdInput
        feature={feature({ dtype: 'str', categories: ['HIGH', 'LOW', 'BOTH', 'NONE'] })}
        op="in"
        value={['LOW']}
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('checkbox', { name: 'LOW' })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'HIGH' }));
    expect(onChange).toHaveBeenLastCalledWith(['HIGH', 'LOW']);
    await userEvent.click(screen.getByRole('checkbox', { name: 'LOW' }));
    expect(onChange).toHaveBeenLastCalledWith(undefined); // nothing chosen is an unset threshold
    rerender(
      <ThresholdInput
        feature={feature({ dtype: 'str' })}
        op="in"
        value={undefined}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByRole('textbox', { name: 'Values, separated by commas' }),
    ).toBeInTheDocument();
  });

  it('takes free text for a text field without categories', async () => {
    const onChange = vi.fn();
    render(
      <ThresholdInput feature={feature({ dtype: 'str' })} op="eq" value="" onChange={onChange} />,
    );
    await userEvent.type(screen.getByRole('textbox', { name: 'Threshold' }), 'X');
    expect(onChange).toHaveBeenCalledWith('X');
  });
});
