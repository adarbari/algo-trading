import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '@algotrade/ui';

import type { CatalogueFeature, GuideUse } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { CriterionRow } from './CriterionRow';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, gql: vi.fn() };
});

const CATALOGUE = [
  {
    name: 'rollup.iv30@v1.iv30',
    dtype: 'float',
    description: 'Our 30-day IV',
    unit: 'decimal',
    group: 'iv30@v1',
    scope: 'site',
    licence: 'open',
    categories: [],
    guide: {
      theme: 'volatility',
      reads: 'Our 30-day ATM implied volatility as a fraction.',
      uses: [
        {
          intent: 'high IV',
          op: 'gte',
          value: 0.4,
          mode: 'soft',
          tolerance: 0.05,
          onMiss: null,
          note: '',
        },
      ],
      caveats: ['A report inside 30 days inflates it.'],
      sources: [],
    },
  },
  {
    name: 'instrument.sector',
    dtype: 'str',
    description: 'Sector',
    unit: null,
    group: null,
    scope: 'site',
    licence: 'open',
    categories: [],
  },
] as unknown as CatalogueFeature[];

const USE: GuideUse = {
  intent: 'high IV',
  op: 'gte',
  value: 0.4,
  mode: 'soft',
  tolerance: 0.05,
  onMiss: null,
  note: '',
};

const CRITERION: Criterion = {
  id: 'iv30',
  field: 'rollup.iv30@v1.iv30',
  op: 'gte',
  mode: 'hard',
  value: 0.5,
};

function setup(
  criterion: Criterion = CRITERION,
  extra: Partial<ComponentProps<typeof CriterionRow>> = {},
) {
  const onChange = vi.fn();
  const onRemove = vi.fn();
  const view = render(
    <TestQueryProvider>
      <CriterionRow
        criterion={criterion}
        catalogue={CATALOGUE}
        onChange={onChange}
        onRemove={onRemove}
        {...extra}
      />
    </TestQueryProvider>,
  );
  return { onChange, onRemove, ...view };
}

describe('CriterionRow', () => {
  it('shows the feature, its description and unit, the operator and the threshold', async () => {
    const { container } = setup();
    expect(screen.getByRole('combobox', { name: 'Feature or formula' })).toHaveValue('IV30');
    expect(screen.getByText(/Our 30-day IV · fraction/)).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'Threshold' })).toHaveValue('50.0');
    expect(screen.getByRole('radio', { name: 'Hard' })).toBeChecked();
    await expectNoA11yViolations(container);
  });

  it('a soft mode starts with a zero tolerance and shows the tolerance fields', async () => {
    const { onChange, rerender } = setup();
    await userEvent.click(screen.getByRole('radio', { name: 'Soft' }));
    expect(onChange).toHaveBeenCalledWith({
      ...CRITERION,
      mode: 'soft',
      tolerance: 0,
      on_miss: undefined,
    });
    rerender(
      <TestQueryProvider>
        <CriterionRow
          criterion={{ ...CRITERION, mode: 'soft', tolerance: 0.05 }}
          catalogue={CATALOGUE}
          onChange={onChange}
          onRemove={vi.fn()}
        />
      </TestQueryProvider>,
    );
    expect(screen.getByRole('spinbutton', { name: 'Tolerance' })).toBeInTheDocument();
  });

  it('changing the operator keeps a number threshold; a list operator resets it', async () => {
    const { onChange } = setup();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Operator' }), 'lt');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ op: 'lt', value: 0.5 }));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Operator' }), 'between');
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ op: 'between', value: undefined, mode: 'hard' }),
    );
  });

  it('switching to a text field fixes the operator and removes the tolerance', async () => {
    const { onChange } = setup({ ...CRITERION, mode: 'soft', tolerance: 0.1 });
    await userEvent.click(screen.getByRole('combobox', { name: 'Feature or formula' }));
    await userEvent.click(screen.getByRole('option', { name: /instrument\.sector/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        field: 'instrument.sector',
        op: 'eq',
        mode: 'hard',
        tolerance: undefined,
      }),
    );
  });

  it('removes the criterion and shows the error that names it', async () => {
    const { onRemove } = setup(CRITERION, { error: 'my.criteria.iv30.field: unknown field' });
    expect(screen.getByText('my.criteria.iv30.field: unknown field')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Remove criterion iv30' }));
    expect(onRemove).toHaveBeenCalled();
  });

  it('loads the distribution only when it is opened, with the threshold marked', async () => {
    vi.mocked(gql).mockResolvedValue({
      distribution: {
        name: 'rollup.iv30@v1.iv30',
        session: '2026-10-02',
        count: 100,
        nulls: 0,
        quantiles: [{ q: 0.5, value: 0.4 }],
        histogram: [{ lo: 0, hi: 1, count: 10 }],
        categories: [],
        unknown: null,
      },
    });
    setup();
    expect(gql).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Distribution/ }));
    expect(
      await screen.findByRole('img', { name: /rollup\.iv30@v1\.iv30 across 100 instruments/ }),
    ).toBeInTheDocument();
  });

  it('puts the help slot beside the field, and its "Use this" sets the row to the intent', async () => {
    const renderFieldHelp = vi.fn((field: string, onUse: (use: GuideUse) => void) => (
      <IconButton
        icon="info"
        label={`What is ${field}?`}
        size="sm"
        onClick={() => {
          onUse(USE);
        }}
      />
    ));
    const { onChange, container } = setup(CRITERION, { renderFieldHelp });
    expect(renderFieldHelp).toHaveBeenCalledWith('rollup.iv30@v1.iv30', expect.any(Function));
    await userEvent.click(screen.getByRole('button', { name: /^What is rollup\.iv30/ }));
    expect(onChange).toHaveBeenCalledWith({
      ...CRITERION,
      op: 'gte',
      value: 0.4,
      mode: 'soft',
      tolerance: 0.05,
      on_miss: undefined,
    });
    await expectNoA11yViolations(container);
  });

  it('shows no help for a field without a guide', () => {
    const renderFieldHelp = vi.fn(() => <span>help</span>);
    setup(
      { ...CRITERION, field: 'instrument.sector', op: 'eq', value: 'Tech' },
      { renderFieldHelp },
    );
    expect(renderFieldHelp).not.toHaveBeenCalled();
  });

  it('is read-only for a preset not yet copied', () => {
    setup(CRITERION, { disabled: true });
    expect(screen.getByRole('button', { name: 'Remove criterion iv30' })).toBeDisabled();
    expect(screen.getByRole('spinbutton', { name: 'Threshold' })).toBeDisabled();
  });
});
