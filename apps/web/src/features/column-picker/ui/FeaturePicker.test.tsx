import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { FeaturePicker } from './FeaturePicker';

const hooks = vi.hoisted(() => ({ useFeatureCatalogue: vi.fn() }));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
}));

const base = {
  source: 'x',
  nullMeaning: '',
  version: 1,
  group: null,
  key: null,
  inputs: [],
  range: null,
  categories: [],
  owner: null,
  dtype: 'float',
};

beforeEach(() => {
  hooks.useFeatureCatalogue.mockReturnValue(
    fakeQuery([
      {
        ...base,
        name: 'feature.market_cap',
        kind: 'expression',
        unit: 'usd',
        description: 'shares x close',
        scope: 'site',
      },
      {
        ...base,
        name: 'feature.my_ratio',
        kind: 'expression',
        unit: 'ratio',
        description: 'Mine',
        scope: 'user',
      },
    ]),
  );
});

describe('FeaturePicker', () => {
  it('adds a feature from the catalogue and removes chosen ones', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FeaturePicker label="Columns" chosen={['feature.my_ratio']} onChange={onChange} />);
    await user.click(screen.getByRole('button', { name: 'Columns' }));
    const dialog = screen.getByRole('dialog', { name: 'Columns' });
    expect(screen.getByText('My ratio · yours')).toBeInTheDocument();
    await user.type(screen.getByRole('combobox'), 'market');
    await user.keyboard('{ArrowDown}{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(['feature.my_ratio', 'feature.market_cap']);
    await user.click(screen.getByRole('button', { name: 'Remove My ratio · yours' }));
    expect(onChange).toHaveBeenLastCalledWith([]);
    await expectNoA11yViolations(dialog);
  });
});
