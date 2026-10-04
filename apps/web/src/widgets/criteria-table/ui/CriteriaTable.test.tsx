import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { CriteriaTable } from './CriteriaTable';

const state = vi.hoisted(() => ({ builder: {} as Record<string, unknown>, catalogue: vi.fn() }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => state.builder,
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: state.catalogue,
}));
vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn(), GET: vi.fn() } };
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
  },
  {
    name: 'rollup.price_stats@v2.close',
    dtype: 'float',
    description: 'Close',
    unit: 'usd_per_share',
    group: 'price_stats@v2',
    scope: 'site',
    licence: 'open',
    categories: [],
  },
] as unknown as CatalogueFeature[];

const setCriterion = vi.fn();
const removeCriterion = vi.fn();
const addCriterion = vi.fn();
const setTieBreak = vi.fn();
const builder = (patch: Record<string, unknown> = {}) => ({
  status: 'ready',
  readOnly: false,
  selection: 'liquid_optionable',
  criteria: [
    { id: 'iv30', field: 'rollup.iv30@v1.iv30', op: 'gte', mode: 'hard', value: 0.5 },
    { id: 'close', field: 'rollup.price_stats@v2.close', op: 'gt', mode: 'hard', value: 5 },
  ],
  tieBreak: { field: null, order: 'desc' },
  errorCriterion: null,
  preview: { error: null },
  retry: vi.fn(),
  setCriterion,
  removeCriterion,
  addCriterion,
  setTieBreak,
  ...patch,
});

function setup() {
  return render(
    <TestQueryProvider>
      <CriteriaTable />
    </TestQueryProvider>,
  );
}

beforeEach(() => {
  for (const mock of [setCriterion, removeCriterion, addCriterion, setTieBreak]) mock.mockReset();
  state.builder = builder();
  state.catalogue.mockReturnValue(fakeQuery(CATALOGUE));
  vi.mocked(api.POST).mockReset();
});

describe('CriteriaTable', () => {
  it('reads the screen back in plain English and lists each criterion', async () => {
    const { container } = setup();
    expect(
      screen.getByText('Find instruments in liquid_optionable where IV30 ≥ 50% and Close > $5.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('radiogroup', { name: /Mode of/ })).toHaveLength(2);
    expect(
      screen.getByText(
        'Universe: liquid_optionable. The preview runs on the latest closed session.',
      ),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('adds and removes criteria', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: '+ Add criterion' }));
    expect(addCriterion).toHaveBeenCalledWith();
    await userEvent.click(screen.getByRole('button', { name: 'Remove criterion close' }));
    expect(removeCriterion).toHaveBeenCalledWith('close');
  });

  it('edits a criterion through its row', async () => {
    setup();
    await userEvent.click(screen.getAllByRole('radio', { name: 'Score' })[0] as HTMLElement);
    expect(setCriterion).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'iv30', mode: 'score' }),
    );
  });

  it('adds a formula feature as a new criterion', async () => {
    vi.mocked(api.POST).mockResolvedValue({
      data: {
        name: 'vol_gap',
        field: 'feature.vol_gap',
        theme: 'builder',
        dtype: 'float32',
        kind: 'expression',
        inputs: [],
      },
      response: new Response(null, { status: 201 }),
    } as never);
    setup();
    await userEvent.click(screen.getByRole('button', { name: '+ Add formula feature' }));
    expect(screen.getByRole('dialog', { name: 'Add formula feature' })).toBeInTheDocument();
  });

  it('shows the empty state with no criteria', () => {
    state.builder = builder({ criteria: [] });
    setup();
    expect(screen.getByText('No criteria yet')).toBeInTheDocument();
    expect(screen.queryByText(/Find instruments/)).toBeNull();
  });

  it('puts the preview error on the criterion it names', () => {
    state.builder = builder({
      errorCriterion: 'close',
      preview: { error: 'my.criteria.close.field: unknown field' },
    });
    setup();
    expect(screen.getAllByText('my.criteria.close.field: unknown field')).toHaveLength(1);
  });

  it('locks a preset that has not been copied', () => {
    state.builder = builder({ readOnly: true });
    setup();
    expect(screen.getByRole('button', { name: '+ Add criterion' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remove criterion iv30' })).toBeDisabled();
  });

  it('shows loading and the load error', () => {
    state.builder = builder({ status: 'loading' });
    const { rerender } = setup();
    expect(screen.getByText('Loading the screener…')).toBeInTheDocument();
    state.builder = builder({ status: 'error' });
    rerender(
      <TestQueryProvider>
        <CriteriaTable />
      </TestQueryProvider>,
    );
    expect(screen.getByText('The screener failed to load.')).toBeInTheDocument();
  });
});
