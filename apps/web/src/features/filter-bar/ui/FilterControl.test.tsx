import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { FilterDefinition } from '@/entities/filter';
import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { FilterControl, type FilterControlProps } from './FilterControl';

const base: FilterDefinition = {
  id: 'x',
  label: 'Thing',
  group: 'SETUP',
  kind: 'PICK',
  guide: 'term:filter_x',
  options: [],
  bins: [],
  windowUnit: null,
  unit: null,
};

const facet = {
  id: 'x',
  active: true,
  removes: null,
  unknown: 4,
  options: [
    { value: 'a', count: 7 },
    { value: 'b', count: 2 },
  ],
  bins: [
    { lo: 0, hi: 10, count: 5 },
    { lo: 10, hi: 20, count: 3 },
  ],
};

function setup(definition: Partial<FilterDefinition>, props: Partial<FilterControlProps> = {}) {
  const onChange = vi.fn();
  const onRemove = vi.fn();
  const view = render(
    <FilterControl
      definition={{ ...base, ...definition }}
      filter={undefined}
      facet={facet}
      onChange={onChange}
      onRemove={onRemove}
      help={<Text>help</Text>}
      unknownHelp={<Text>unknown help</Text>}
      {...props}
    />,
  );
  return { ...view, onChange, onRemove };
}

stubElementSize();

describe('FilterControl', () => {
  it('pick: lists the stored values with the served counts, toggles one, removes the last', async () => {
    const user = userEvent.setup();
    const { onChange, onRemove, container } = setup({ kind: 'PICK' });
    expect(screen.getByRole('button', { name: /a\s*7/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /b\s*2/ }));
    expect(onChange).toHaveBeenCalledWith({ values: ['b'] });
    await expectNoA11yViolations(container);
    expect(onRemove).not.toHaveBeenCalled();
    const again = setup({ kind: 'PICK' }, { filter: { id: 'x', values: ['a'], active: true } });
    await user.click(screen.getAllByRole('button', { name: /a\s*7/ }).at(-1) as HTMLElement);
    expect(again.onRemove).toHaveBeenCalled();
  });

  it('pick: names the options by the definition when it has them', () => {
    setup({ kind: 'PICK', options: [{ value: 'a', label: 'Alpha' }] });
    expect(screen.getByRole('button', { name: /Alpha\s*7/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^b/ })).not.toBeInTheDocument();
  });

  it('toggle: either removes, yes and no set the value', async () => {
    const user = userEvent.setup();
    const { onChange, onRemove } = setup({ kind: 'TOGGLE' });
    await user.click(screen.getByRole('radio', { name: 'Yes' }));
    expect(onChange).toHaveBeenCalledWith({ values: ['yes'] });
    await user.click(screen.getByRole('radio', { name: 'No' }));
    expect(onChange).toHaveBeenLastCalledWith({ values: ['no'] });
    expect(screen.getByRole('radio', { name: 'Either' })).toBeInTheDocument();
    expect(onRemove).not.toHaveBeenCalled();
  });

  it('select: any removes the filter', async () => {
    const user = userEvent.setup();
    const { onRemove } = setup(
      { kind: 'SELECT', options: [{ value: 'a', label: 'Alpha' }] },
      { filter: { id: 'x', values: ['a'], active: true } },
    );
    await user.selectOptions(screen.getByRole('combobox', { name: 'Thing' }), 'Any');
    expect(onRemove).toHaveBeenCalled();
  });

  it('range: sets the ends, shows the unknown count with its help, and empty removes it', async () => {
    const user = userEvent.setup();
    const { onChange, onRemove } = setup({ kind: 'RANGE', bins: [0, 10, 20] });
    expect(screen.getByText('Unknown: 4')).toBeInTheDocument();
    expect(screen.getByText('unknown help')).toBeInTheDocument();
    await user.type(screen.getByRole('spinbutton', { name: 'Min' }), '5{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ min: 5, max: undefined });
    expect(onRemove).not.toHaveBeenCalled();
    onChange.mockClear();
    const again = setup(
      { kind: 'RANGE', bins: [0, 10, 20] },
      { filter: { id: 'x', min: 5, active: true } },
    );
    const min = again.getAllByRole('spinbutton', { name: 'Min' }).at(-1) as HTMLElement;
    await user.clear(min);
    await user.tab();
    expect(again.onRemove).toHaveBeenCalled();
  });

  it('window: sets the amount in the definition’s unit, and empty removes it', async () => {
    const user = userEvent.setup();
    const { onChange, onRemove } = setup({ kind: 'WINDOW', windowUnit: 'SESSIONS' });
    expect(screen.getByRole('radio', { name: 'sessions' })).toBeChecked();
    await user.type(screen.getByRole('spinbutton', { name: 'Thing' }), '5{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ within: { amount: 5, unit: 'sessions' } });
    expect(onRemove).not.toHaveBeenCalled();
  });

  it('shows the filter’s name with its help button', () => {
    setup({ kind: 'TOGGLE' });
    expect(screen.getByText('Thing')).toBeInTheDocument();
    expect(screen.getByText('help')).toBeInTheDocument();
  });
});
