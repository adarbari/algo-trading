import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature } from '@/entities/feature';
import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { CriteriaTable } from './CriteriaTable';

const state = vi.hoisted(() => ({ builder: {}, catalogue: vi.fn() }));

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
const reviewFormula = vi.fn();
const skipFormula = vi.fn();
const CRITERIA = [
  { id: 'iv30', field: 'rollup.iv30@v1.iv30', op: 'gte', mode: 'hard', value: 0.5 },
  { id: 'close', field: 'rollup.price_stats@v2.close', op: 'gt', mode: 'hard', value: 5 },
];
const joinWithPrevious = vi.fn();
const excludeCriterion = vi.fn();
const excludeGroup = vi.fn();
const ungroup = vi.fn();
const builder = (patch: Record<string, unknown> = {}) => {
  const criteria = (patch['criteria'] as typeof CRITERIA | undefined) ?? CRITERIA;
  return base({
    layout: criteria.map((criterion) => ({ type: 'criterion', criterion })),
    ...patch,
  });
};
const base = (patch: Record<string, unknown>) => ({
  status: 'ready',
  preset: null,
  criteria: CRITERIA,
  groups: [],
  canJoinPrevious: (id: string) => id === 'close',
  joinWithPrevious,
  excludeCriterion,
  excludeGroup,
  ungroup,
  tieBreak: { field: null, order: 'desc' },
  errorCriterion: null,
  preview: { error: null },
  retry: vi.fn(),
  setCriterion,
  removeCriterion,
  addCriterion,
  setTieBreak,
  pendingFormulas: [],
  reviewFormula,
  skipFormula,
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
  for (const mock of [
    joinWithPrevious,
    excludeCriterion,
    excludeGroup,
    ungroup,
    setCriterion,
    removeCriterion,
    addCriterion,
    setTieBreak,
    reviewFormula,
    skipFormula,
  ])
    mock.mockReset();
  state.builder = builder();
  state.catalogue.mockReturnValue(fakeQuery(CATALOGUE));
  vi.mocked(api.POST).mockReset();
});

describe('CriteriaTable', () => {
  it('reads the screen back in plain English and lists each criterion', async () => {
    const { container } = setup();
    expect(
      screen.getByText('Find instruments where IV30 ≥ 50% and Close > $5.'),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('radiogroup', { name: /Mode of/ })).toHaveLength(2);
    expect(screen.getByText('The preview runs on the latest closed session.')).toBeInTheDocument();
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
    });
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

  it('keeps a preset editable: the first edit makes the copy', () => {
    state.builder = builder({ preset: { id: 'vrp', version: 1 } });
    setup();
    expect(screen.getByRole('button', { name: '+ Add criterion' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Remove criterion iv30' })).toBeEnabled();
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

  describe('a formula the draft proposed and the trader has not decided', () => {
    const FORMULA = {
      name: 'draft_near_high',
      criterion: { field: 'feature.draft_near_high', op: 'gte', value: -0.05, mode: 'hard' },
    };

    it('waits as a pending row that is not in the plain-English sentence', async () => {
      state.builder = builder({ pendingFormulas: [FORMULA] });
      const { container } = setup();
      expect(
        screen.getByRole('group', { name: 'Waiting on formula: feature.draft_near_high' }),
      ).toBeInTheDocument();
      expect(screen.getAllByRole('radiogroup', { name: /Mode of/ })).toHaveLength(2);
      expect(screen.queryByText(/draft_near_high/, { selector: 'p' })).toBeNull();
      await expectNoA11yViolations(container);
    });

    it('opens the review or skips it from the row', async () => {
      state.builder = builder({ pendingFormulas: [FORMULA] });
      setup();
      await userEvent.click(screen.getByRole('button', { name: 'Review and add' }));
      expect(reviewFormula).toHaveBeenCalledWith(FORMULA);
      await userEvent.click(screen.getByRole('button', { name: 'Skip' }));
      expect(skipFormula).toHaveBeenCalledWith('draft_near_high');
    });

    it('shows no row for a formula with no criterion, and no empty state beside one', () => {
      state.builder = builder({ pendingFormulas: [{ name: 'draft_x', criterion: null }] });
      setup();
      expect(screen.queryByRole('group', { name: /Waiting on formula/ })).toBeNull();
      state.builder = builder({ criteria: [], pendingFormulas: [FORMULA] });
      setup();
      expect(screen.queryByText('No criteria yet')).toBeNull();
    });
  });

  describe('groups (ADR 0071)', () => {
    const [iv30, close] = CRITERIA as [(typeof CRITERIA)[number], (typeof CRITERIA)[number]];
    const any = { id: 'any', kind: 'any', members: ['iv30', 'close'] };
    const grouped = (mode: string, extra: Record<string, unknown> = {}) => {
      const criteria = [iv30, { ...close, mode }];
      return builder({
        criteria,
        groups: [any],
        layout: [
          {
            type: 'group',
            group: any,
            editable: true,
            owned: true,
            members: criteria.map((criterion) => ({ type: 'criterion', criterion })),
          },
        ],
        ...extra,
      });
    };

    it('offers the grouping actions on a loose criterion', async () => {
      setup();
      expect(screen.getAllByRole('button', { name: 'Exclude (none of)' })).toHaveLength(2);
      await userEvent.click(screen.getByRole('button', { name: 'Either this or the previous' }));
      expect(joinWithPrevious).toHaveBeenCalledWith('close');
      await userEvent.click(
        screen.getAllByRole('button', { name: 'Exclude (none of)' })[0] as HTMLElement,
      );
      expect(excludeCriterion).toHaveBeenCalledWith('iv30');
    });

    it('shows one level in place, each member with its own mode control', async () => {
      state.builder = grouped('hard');
      const { container } = setup();
      const group = screen.getByRole('region', { name: /IV30 ≥ 50% or Close > \$5/ });
      expect(group).toHaveTextContent('Any of');
      expect(screen.getAllByRole('radiogroup', { name: /Mode of/ })).toHaveLength(2);
      expect(screen.queryByText('Never rejects')).toBeNull();
      await userEvent.click(screen.getByRole('button', { name: 'Ungroup' }));
      expect(ungroup).toHaveBeenCalledWith('any');
      await userEvent.click(screen.getByRole('button', { name: 'Exclude (none of)' }));
      expect(excludeGroup).toHaveBeenCalledWith(any);
      await expectNoA11yViolations(container);
    });

    it('labels an any with a score member as never rejecting', () => {
      state.builder = grouped('score');
      setup();
      expect(screen.getByText('Never rejects')).toBeInTheDocument();
    });

    it("shows a deeper group as one read-only row that ungroups when it is the draft's", async () => {
      const inner = { id: 'dip', kind: 'all', members: ['iv30', 'close'] };
      const outer = { id: 'either', kind: 'any', members: ['dip', 'extra'] };
      const extra = {
        id: 'extra',
        field: 'rollup.iv30@v1.iv30',
        op: 'lt',
        mode: 'hard',
        value: 0.1,
      };
      const criteria = [iv30, close, extra];
      const leaf = (criterion: (typeof criteria)[number]) => ({ type: 'criterion', criterion });
      state.builder = builder({
        criteria,
        groups: [inner, outer],
        layout: [
          {
            type: 'group',
            group: outer,
            editable: false,
            owned: true,
            members: [
              {
                type: 'group',
                group: inner,
                editable: false,
                owned: true,
                members: [leaf(iv30), leaf(close)],
              },
              leaf(extra),
            ],
          },
        ],
      });
      const { container } = setup();
      expect(screen.queryAllByRole('radiogroup', { name: /Mode of/ })).toHaveLength(0);
      expect(
        screen.getAllByText(/\(IV30 ≥ 50% and Close > \$5\) or IV30 < 10%/).length,
      ).toBeGreaterThan(0);
      await userEvent.click(screen.getByRole('button', { name: 'Ungroup' }));
      expect(ungroup).toHaveBeenCalledWith('either');
      await expectNoA11yViolations(container);
    });
  });
});
