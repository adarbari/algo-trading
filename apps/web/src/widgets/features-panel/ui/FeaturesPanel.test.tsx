import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { FeaturesPanel } from './FeaturesPanel';

const hooks = vi.hoisted(() => ({
  useFeatureCatalogue: vi.fn(),
  useFeatureDistribution: vi.fn(),
  useInstrument: vi.fn(),
  useFeatureHistory: vi.fn(),
}));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: hooks.useFeatureCatalogue,
  useFeatureDistribution: hooks.useFeatureDistribution,
}));
vi.mock('@/entities/instrument', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useInstrument: hooks.useInstrument,
  useFeatureHistory: hooks.useFeatureHistory,
}));

const IV30 = 'rollup.iv30@v1.iv30';
const base = {
  source: 'x',
  null_meaning: '',
  version: 1,
  group: null,
  key: null,
  inputs: [],
  range: null,
  categories: [],
  owner: null,
};

stubElementSize();

beforeEach(() => {
  hooks.useFeatureCatalogue.mockReturnValue(
    fakeQuery([
      {
        ...base,
        name: 'instrument.sector',
        kind: 'instrument',
        dtype: 'str',
        unit: null,
        description: 'company detail (SEC EDGAR)',
        scope: 'site',
      },
      {
        ...base,
        name: IV30,
        kind: 'chain',
        dtype: 'float',
        unit: 'decimal',
        description: 'Our 30-day ATM implied volatility',
        scope: 'site',
      },
      {
        ...base,
        name: 'feature.my_ratio',
        kind: 'expression',
        dtype: 'float',
        unit: 'ratio',
        description: 'My ratio',
        scope: 'user',
        licence: 'personal',
        owner: 'bob',
      },
    ]),
  );
  hooks.useInstrument.mockReturnValue(
    fakeQuery({
      instrument_id: 'EQ:A',
      reference: { symbol: 'AAPL' },
      company: { sector: 'Technology' },
      features: { [IV30]: 0.244, 'feature.my_ratio': 1.5 },
      feature_sessions: {},
      reference_snapshot: '2026-10-02',
    }),
  );
  hooks.useFeatureHistory.mockReturnValue(
    fakeQuery({ items: [{ [IV30]: 0.22 }, { [IV30]: 0.23 }, { [IV30]: 0.244 }] }),
  );
  hooks.useFeatureDistribution.mockReturnValue(
    fakeQuery({
      name: IV30,
      dtype: 'float',
      session: '2026-10-02',
      count: 3625,
      nulls: 1654,
      quantiles: { '0.5': 0.47 },
      histogram: [{ lo: 0, hi: 1, count: 1971 }],
      categories: [],
    }),
  );
});

describe('FeaturesPanel', () => {
  it('lists every catalogue feature with value, history and definition', async () => {
    const onFeatureChange = vi.fn();
    const { container } = render(
      <FeaturesPanel symbol="AAPL" feature={null} onFeatureChange={onFeatureChange} />,
    );
    const grid = screen.getByRole('grid', { name: 'AAPL features' });
    const rows = within(grid).getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('IV30 (ours)');
    expect(rows[0]).toHaveTextContent('24.4%');
    expect(
      within(grid).getByRole('img', { name: /AAPL IV30 \(ours\), 3 sessions/ }),
    ).toBeInTheDocument();
    expect(within(grid).getByText('My ratio · yours · personal licence')).toBeInTheDocument();
    expect(rows.at(-1)).toHaveTextContent('Technology');
    expect(screen.getByText('Choose a feature')).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.setup().click(within(grid).getByText('IV30 (ours)'));
    expect(onFeatureChange).toHaveBeenCalledWith(IV30);
  });

  it('shows the chosen feature across the universe with the ticker marked', async () => {
    const { container } = render(
      <FeaturesPanel symbol="AAPL" feature={IV30} onFeatureChange={vi.fn()} />,
    );
    expect(
      screen.getByRole('heading', { name: 'IV30 (ours) across the universe' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /IV30 \(ours\) across 1,971 tickers/ }),
    ).toBeInTheDocument();
    expect(hooks.useFeatureDistribution).toHaveBeenCalledWith(IV30);
    await expectNoA11yViolations(container);
  });

  it('filters features by name or definition', async () => {
    render(<FeaturesPanel symbol="AAPL" feature={null} onFeatureChange={vi.fn()} />);
    await userEvent
      .setup()
      .type(screen.getByRole('searchbox', { name: 'Filter features' }), 'implied');
    const grid = screen.getByRole('grid', { name: 'AAPL features' });
    expect(within(grid).getAllByRole('row')).toHaveLength(2);
  });
});
