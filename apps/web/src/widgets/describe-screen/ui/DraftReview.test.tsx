import { Text } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenDocument } from '@/entities/screen';
import type { ScreenDraft } from '@/features/screener-describe';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import DraftReview, { type DraftReviewProps } from './DraftReview';

const history = vi.hoisted(() => ({ data: [] as unknown[] }));

vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`guide ${entry.id}`}</Text>,
}));
vi.mock('@/features/screener-describe', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useMyFeatureRequests: () => ({ data: history.data }),
}));

const SENTENCE = 'liquid optionable stocks with a rising moat score';
const FIFTY = { field: 'f.dollar_volume', op: 'gte', value: 50_000_000, mode: 'hard' };
const TEN = { field: 'f.dollar_volume', op: 'gte', value: 10_000_000, mode: 'hard' };
const DOCUMENT: ScreenDocument = {
  id: 'mine',
  criteria: {
    optionable: { field: 'f.optionable', op: 'eq', value: true, mode: 'hard' },
    dollar_volume: { ...FIFTY },
  },
};

const FORMULA = {
  name: 'draft_near_high',
  expr: 'close / high_52w - 1',
  dtype: 'float',
  unit: 'ratio',
  description: 'How near the 52-week high',
  null_meaning: 'no price',
  inputs: ['close', 'high_52w'],
  criterion: null,
  fingerprint: 'abc',
  pending: true,
  dry_run: {
    rows: 13334,
    no_value_rate: 0.062,
    minimum: -0.97,
    maximum: 0,
    criterion_pass: 612,
    session: '2026-10-09',
    sample: [{ instrument_id: 'EQ:AAA', value: -0.02 }],
  },
};

const ANSWER: ScreenDraft = {
  screener_id: 'mine',
  document: DOCUMENT,
  dropped: [{ id: 'iv', field: 'rollup.nope@v1.iv', reason: 'not in the catalogue' }],
  notes: ['assumed US listings'],
  formulas: [FORMULA],
  formulas_dropped: [{ name: 'draft_dup', existing: 'f.x', reason: 'equals f.x' }],
  missing: [
    {
      key: 'moat_score',
      new_key_slug: null,
      span: 'rising moat score',
      description: 'A moat score that rises over time',
      why_needed: 'The sentence asks for a trend in moat',
      closest: ['f.quality'],
      feasibility: 'NEEDS_SOURCE',
    },
  ],
  unresolved: [
    {
      term: 'liquid',
      span: 'liquid',
      default_index: 0,
      alternatives: [
        { text: 'over $50M traded a day', criterion: FIFTY },
        { text: 'over $10M traded a day', criterion: TEN },
      ],
    },
  ],
};

function setup(over: Partial<DraftReviewProps> = {}) {
  const props: DraftReviewProps = {
    answer: ANSWER,
    text: SENTENCE,
    document: DOCUMENT,
    formulaStates: {},
    notes: [],
    onRemoveNote: vi.fn(),
    onReviewFormula: vi.fn(),
    onSkipFormula: vi.fn(),
    onPickReading: vi.fn(),
    renderFieldHelp: (field) => <Text>{`field help ${field}`}</Text>,
    ...over,
  };
  return { props, ...render(<DraftReview {...props} />) };
}

beforeEach(() => {
  history.data = [];
});

describe('DraftReview', () => {
  it('echoes the sentence with the server-named spans tagged by words, not colour alone', async () => {
    const { container } = setup();
    const sentence = screen.getByLabelText('What was understood');
    expect(within(sentence).getByText('liquid')).toBeInTheDocument();
    expect(within(sentence).getByText('needs your call')).toBeInTheDocument();
    expect(within(sentence).getByText('rising moat score')).toBeInTheDocument();
    expect(within(sentence).getByText('not available yet')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the four groups, each with its Guide help', () => {
    setup();
    for (const title of ['Applied', 'Proposed formulas', 'Needs your call', 'Not available yet']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
    for (const id of [
      'describe_applied',
      'describe_proposed_formulas',
      'describe_needs_your_call',
      'describe_not_available_yet',
    ]) {
      expect(screen.getByText(`help ${id}`)).toBeInTheDocument();
    }
  });

  it('lists the applied rows with field help, and what was left out', () => {
    setup();
    expect(screen.getByText('field help f.optionable')).toBeInTheDocument();
    expect(screen.getByText('field help f.dollar_volume')).toBeInTheDocument();
    expect(screen.getByText(/Left out iv \(/)).toBeInTheDocument();
    expect(screen.getByText('Left out draft_dup: equals f.x')).toBeInTheDocument();
    expect(screen.getByText('assumed US listings')).toBeInTheDocument();
    expect(screen.getByText('Loaded in the Builder')).toBeInTheDocument();
  });

  it('lists the notes kept with the screen, each removable', async () => {
    const { props } = setup({ notes: ['A moat score that rises over time'] });
    expect(screen.getByText('help describe_not_covered')).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Remove note: A moat score that rises over time' }),
    );
    expect(props.onRemoveNote).toHaveBeenCalledWith('A moat score that rises over time');
  });

  it('shows the formula with its dry run, and Review and add / Skip call the Builder', async () => {
    const { props } = setup();
    expect(screen.getByText('close / high_52w - 1')).toBeInTheDocument();
    expect(screen.getByText('Inputs: close, high_52w · ratio')).toBeInTheDocument();
    expect(screen.getByText('Pending formula')).toBeInTheDocument();
    expect(screen.getByRole('grid', { name: 'draft_near_high sample rows' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Review and add' }));
    expect(props.onReviewFormula).toHaveBeenCalledWith(FORMULA);
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(props.onSkipFormula).toHaveBeenCalledWith('draft_near_high');
  });

  it('renders a decided formula by its state, without the buttons', () => {
    setup({ formulaStates: { draft_near_high: 'skipped' } });
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review and add' })).not.toBeInTheDocument();
    expect(screen.queryByText('Pending formula')).not.toBeInTheDocument();
  });

  it('preselects the default reading; picking another swaps its row locally and records the choice', async () => {
    const { props, rerender } = setup();
    const group = screen.getByRole('radiogroup', { name: 'Reading of liquid' });
    expect(within(group).getByRole('radio', { name: 'over $50M traded a day' })).toBeChecked();
    await userEvent.click(within(group).getByRole('radio', { name: 'over $10M traded a day' }));
    expect(props.onPickReading).toHaveBeenCalledWith(
      { id: 'dollar_volume', field: 'f.dollar_volume', op: 'gte', value: 10_000_000, mode: 'hard' },
      { event: 'choice_made', subject: 'liquid', picked: 1 },
    );
    expect(within(group).getByRole('radio', { name: 'over $10M traded a day' })).toBeChecked();
    // The Builder applied it: the row now holds the second reading, so a pick back swaps again.
    rerender(
      <DraftReview
        {...props}
        document={{ id: 'mine', criteria: { ...DOCUMENT.criteria, dollar_volume: { ...TEN } } }}
      />,
    );
    await userEvent.click(within(group).getByRole('radio', { name: 'over $50M traded a day' }));
    expect(props.onPickReading).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: 'dollar_volume', value: 50_000_000 }),
      { event: 'choice_made', subject: 'liquid', picked: 0 },
    );
  });

  it('offers no swap once the trader removed the row of the reading', () => {
    setup({ document: { id: 'mine', criteria: {} } });
    for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled();
  });

  it('shows a requested, not applied card with feasibility, and the trader own earlier ask only', () => {
    history.data = [
      {
        ref: 'moat_score',
        description: 'A moat score',
        status: 'OPEN',
        unmapped: false,
        firstAsked: '2026-10-03',
        lastAsked: '2026-10-11',
        timesAsked: 2,
        promotedTo: '',
        feasibility: 'NEEDS_SOURCE',
        span: null,
      },
    ];
    setup();
    expect(screen.getByText('A moat score that rises over time')).toBeInTheDocument();
    expect(screen.getByText('Requested, not applied')).toBeInTheDocument();
    expect(screen.getByText('Needs a new source')).toBeInTheDocument();
    expect(screen.getByText('guide describe_feasibility_source')).toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('You asked for this before, on 3 Oct 2026')).toBeInTheDocument();
    expect(screen.getByText('field help f.quality')).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/other traders|users asked/i);
  });

  it('says nothing about history when the only ask is the one that just ran', () => {
    history.data = [
      {
        ref: 'moat_score',
        description: 'x',
        status: 'OPEN',
        unmapped: false,
        firstAsked: '2026-10-11',
        lastAsked: '2026-10-11',
        timesAsked: 1,
        promotedTo: '',
        feasibility: 'NEEDS_SOURCE',
        span: null,
      },
    ];
    setup();
    expect(screen.queryByText(/You asked for this before/)).not.toBeInTheDocument();
  });

  it('with zero applied criteria shows the groups that have content and no empty screen', () => {
    setup({
      answer: {
        ...ANSWER,
        document: { id: 'mine', criteria: {} },
        dropped: [],
        notes: [],
        formulas: [],
        formulas_dropped: [],
        unresolved: [],
      },
      document: { id: 'mine', criteria: {} },
    });
    expect(screen.getByText('Nothing applied')).toBeInTheDocument();
    expect(screen.queryByText('Loaded in the Builder')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Not available yet' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Proposed formulas' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Needs your call' })).not.toBeInTheDocument();
  });

  it('handles an answer from before the options existed (no formulas, missing or unresolved)', () => {
    const { formulas: _f, formulas_dropped: _d, missing: _m, unresolved: _u, ...old } = ANSWER;
    setup({ answer: old });
    expect(screen.getByRole('heading', { name: 'Applied' })).toBeInTheDocument();
    expect(screen.queryByLabelText('What was understood')).not.toBeInTheDocument();
  });
});
