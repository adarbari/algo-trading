import { Text } from '@algotrade/ui';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenDocument } from '@/entities/screen';
import type { ScreenDraft } from '@/features/screener-describe';
import type { components } from '@/shared/api';
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

type Part = components['schemas']['Part'];

const FIFTY = { field: 'f.dollar_volume', op: 'gte', value: 50_000_000, mode: 'hard' };
const TEN = { field: 'f.dollar_volume', op: 'gte', value: 10_000_000, mode: 'hard' };
const OPTIONABLE = { field: 'f.optionable', op: 'eq', value: true, mode: 'hard' };
const PRICE = { field: 'f.price', op: 'gte', value: 5, mode: 'hard' };
const DOCUMENT: ScreenDocument = {
  id: 'mine',
  rank: { tie_break: 'f.volume' },
  criteria: { dollar_volume: { ...FIFTY }, optionable: { ...OPTIONABLE }, price: { ...PRICE } },
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
    rows: 100,
    no_value_rate: 0.1,
    minimum: -0.9,
    maximum: 0,
    criterion_pass: 12,
    session: '2026-10-09',
    sample: [{ instrument_id: 'EQ:AAA', value: -0.02 }],
  },
};

const SPREAD = { field: 'f.spread', op: 'lte', value: 0.01, mode: 'soft' };
const SUGGESTIONS = [
  { id: 's1', criterion: SPREAD, source: 'spread', why: 'Wide spreads make fills costly' },
  {
    id: 's2',
    criterion: { field: 'f.gap', op: 'lte', value: 3, mode: 'score' },
    source: null,
    why: 'Large gaps raise risk',
  },
  {
    id: 's3',
    criterion: { field: 'f.float', op: 'gte', value: 1, mode: 'hard' },
    source: null,
    why: 'Never offered: hard',
  },
];

const PART: Omit<Part, 'id' | 'kind' | 'words'> = {
  start: 0,
  end: 0,
  rank: false,
  reading: null,
  reading_source: 'model',
  origin: 'words',
  criteria: [],
  dropped: [],
  formulas: [],
  unresolved: [],
  missing: [],
  suggestions: [],
};
const PARTS: Part[] = [
  {
    ...PART,
    id: 'p1',
    words: 'liquid',
    kind: 'needs_choice',
    reading: 'over $50M traded a day',
    criteria: ['dollar_volume'],
    unresolved: ['liquid'],
    suggestions: ['s1'],
  },
  {
    ...PART,
    id: 'p2',
    words: 'optionable stocks',
    kind: 'applied',
    reading: 'stocks with listed options',
    criteria: ['optionable'],
    dropped: ['iv'],
  },
  {
    ...PART,
    id: 'p3',
    words: 'rising moat score',
    kind: 'not_available',
    reading: 'a moat score that keeps rising',
    reading_source: 'server',
    missing: ['moat_score'],
  },
  {
    ...PART,
    id: 'p4',
    words: 'near its high',
    kind: 'formula',
    reading: 'close to the 52-week high',
    formulas: ['draft_near_high'],
  },
  { ...PART, id: 'g1', words: 'blue skies', kind: 'not_understood', origin: 'gap' },
  {
    ...PART,
    id: 'p7',
    words: 'rank by volume',
    kind: 'applied',
    reading: 'highest volume first',
    rank: true,
  },
  {
    ...PART,
    id: 'p6',
    words: '',
    kind: 'applied',
    origin: 'kept',
    reading: 'price at least 5',
    criteria: ['price'],
  },
];

const ANSWER = {
  screener_id: 'mine',
  document: DOCUMENT,
  dropped: [{ id: 'iv', field: 'rollup.nope@v1.iv', reason: 'not in the catalogue' }],
  notes: ['assumed US listings'],
  formulas: [FORMULA],
  formulas_dropped: [],
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
  suggestions: SUGGESTIONS,
  sentence: 'liquid optionable stocks',
  parts: PARTS,
} satisfies ScreenDraft;

function setup(over: Partial<DraftReviewProps> = {}) {
  const props: DraftReviewProps = {
    answer: ANSWER,
    document: DOCUMENT,
    formulaStates: {},
    notes: [],
    onRemoveNote: vi.fn(),
    onReviewFormula: vi.fn(),
    onSkipFormula: vi.fn(),
    onPickReading: vi.fn(),
    onAcceptSuggestion: vi.fn(),
    renderFieldHelp: (field) => <Text>{`field help ${field}`}</Text>,
    ...over,
  };
  return { props, ...render(<DraftReview {...props} />) };
}

const card = (name: string) => screen.getByRole('article', { name });

beforeEach(() => {
  history.data = [];
});

describe('DraftReview with parts', () => {
  it('shows one card per part, in the order of the sentence, in a named list', async () => {
    const { container } = setup();
    const list = screen.getByRole('list', { name: 'Parts of your sentence' });
    const names = within(list)
      .getAllByRole('article')
      .map((a) => a.getAttribute('aria-labelledby'))
      .map((id) => document.getElementById(id ?? '')?.textContent);
    expect(names).toEqual([
      'liquid',
      'optionable stocks',
      'rising moat score',
      'near its high',
      'blue skies',
      'rank by volume',
      'Kept from your screen',
    ]);
    expect(screen.queryByRole('heading', { name: 'Applied' })).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('quotes the trader words, reads the part in plain language and badges its kind with Guide help', () => {
    setup();
    const liquid = card('liquid');
    expect(within(liquid).getByText('Needs your call')).toBeInTheDocument();
    expect(within(liquid).getByText(/We read this as/)).toBeInTheDocument();
    expect(within(liquid).getAllByText(/over \$50M traded a day/).length).toBeGreaterThan(0);
    expect(within(liquid).getByText('guide describe_needs_your_call')).toBeInTheDocument();
    expect(within(card('near its high')).getByText('Formula to review')).toBeInTheDocument();
    expect(within(card('rising moat score')).getByText('Not available yet')).toBeInTheDocument();
  });

  it('a reading the server wrote shows the check-this-reading note, with its Guide help', () => {
    setup();
    const moat = card('rising moat score');
    expect(within(moat).getByText(/Check this reading/)).toBeInTheDocument();
    expect(within(moat).getByText('guide describe_part_reading')).toBeInTheDocument();
    expect(within(card('liquid')).queryByText(/Check this reading/)).not.toBeInTheDocument();
  });

  it('a part nothing understood is a not understood card with no reading text of its own', () => {
    setup();
    const none = card('blue skies');
    expect(within(none).getByText('Not understood')).toBeInTheDocument();
    expect(within(none).getByText('guide describe_part_not_understood')).toBeInTheDocument();
    expect(within(none).queryByText(/over|stocks/)).not.toBeInTheDocument();
  });

  it('a gap card quotes the uncovered words as not understood', () => {
    setup();
    expect(within(card('blue skies')).getByText('Not understood')).toBeInTheDocument();
  });

  it('the part holding the tie-break shows what the screen ranks by', () => {
    setup();
    const rank = card('rank by volume');
    expect(within(rank).getByText('Ranked by')).toBeInTheDocument();
    expect(within(rank).getByText('field help f.volume')).toBeInTheDocument();
    expect(within(rank).getByText('help describe_part_rank')).toBeInTheDocument();
    expect(within(card('liquid')).queryByText('Ranked by')).not.toBeInTheDocument();
  });

  it('criteria kept from the screen are a card with a title, not quoted words', () => {
    setup();
    const kept = card('Kept from your screen');
    expect(within(kept).queryByText('Kept from your screen', { selector: 'mark' })).toBeNull();
    expect(within(kept).getByText('field help f.price')).toBeInTheDocument();
    expect(within(kept).getByText('Not from the sentence')).toBeInTheDocument();
    expect(within(kept).getByText('help describe_part_kept')).toBeInTheDocument();
  });

  it("lists a part's criteria by id with field help and what was left out of it", () => {
    setup();
    const part = card('optionable stocks');
    expect(within(part).getByText('field help f.optionable')).toBeInTheDocument();
    expect(within(part).getByText(/Left out iv \(/)).toBeInTheDocument();
    expect(within(card('liquid')).getByText('field help f.dollar_volume')).toBeInTheDocument();
  });

  it('shows the part formula with Review and add / Skip, and by its state once decided', async () => {
    const { props, unmount } = setup();
    const part = card('near its high');
    expect(within(part).getByText('close / high_52w - 1')).toBeInTheDocument();
    await userEvent.click(within(part).getByRole('button', { name: 'Review and add' }));
    expect(props.onReviewFormula).toHaveBeenCalledWith(FORMULA);
    await userEvent.click(within(part).getByRole('button', { name: 'Skip' }));
    expect(props.onSkipFormula).toHaveBeenCalledWith('draft_near_high');
    unmount();
    setup({ formulaStates: { draft_near_high: 'accepted' } });
    expect(screen.getByText('Accepted')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review and add' })).not.toBeInTheDocument();
  });

  it('shows the missing feature in its part, with only the trader own earlier ask', () => {
    history.data = [
      {
        ref: 'moat_score',
        description: 'A moat score',
        status: 'OPEN',
        unmapped: false,
        firstAsked: '2026-10-03',
        lastAsked: '2026-10-11',
        timesAsked: 2,
        askedBeforeToday: true,
        promotedTo: '',
        feasibility: 'NEEDS_SOURCE',
        span: null,
      },
    ];
    setup();
    const moat = card('rising moat score');
    expect(within(moat).getByText('A moat score that rises over time')).toBeInTheDocument();
    expect(within(moat).getByText('Requested, not applied')).toBeInTheDocument();
    expect(within(moat).getByText('Needs a new source')).toBeInTheDocument();
    expect(within(moat).getByText('You asked for this before, on 3 Oct 2026')).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/other traders|users asked/i);
  });

  it('picking another reading swaps the row locally and records the choice; the card is not edited', async () => {
    const { props } = setup();
    const group = within(card('liquid')).getByRole('radiogroup', { name: 'Reading of liquid' });
    expect(within(group).getByRole('radio', { name: 'over $50M traded a day' })).toBeChecked();
    await userEvent.click(within(group).getByRole('radio', { name: 'over $10M traded a day' }));
    expect(props.onPickReading).toHaveBeenCalledWith(
      { id: 'dollar_volume', field: 'f.dollar_volume', op: 'gte', value: 10_000_000, mode: 'hard' },
      { event: 'choice_made', subject: 'liquid', picked: 1 },
    );
    expect(within(group).getByRole('radio', { name: 'over $10M traded a day' })).toBeChecked();
  });

  it('offers no swap once the trader removed the row of the reading', () => {
    setup({ document: { id: 'mine', criteria: {} } });
    for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled();
  });

  it('marks a card edited when its rows differ from the answer, and not for a reading pick', () => {
    const { unmount } = setup({
      document: {
        id: 'mine',
        criteria: { ...DOCUMENT.criteria, optionable: { ...OPTIONABLE, mode: 'soft' } },
      },
    });
    expect(within(card('optionable stocks')).getByText('Edited')).toBeInTheDocument();
    expect(
      within(card('optionable stocks')).getByText('guide describe_part_edited'),
    ).toBeInTheDocument();
    expect(within(card('liquid')).queryByText('Edited')).not.toBeInTheDocument();
    unmount();
    setup({
      document: { id: 'mine', criteria: { ...DOCUMENT.criteria, dollar_volume: { ...TEN } } },
    });
    expect(screen.queryByText('Edited')).not.toBeInTheDocument();
  });

  describe('suggestions', () => {
    it('shows soft and score checks in their part, never a hard one, each with its why', () => {
      setup();
      const group = within(card('liquid'));
      expect(group.getByText('Suggested')).toBeInTheDocument();
      expect(group.getByText('help describe_suggested')).toBeInTheDocument();
      expect(group.getByText('Wide spreads make fills costly')).toBeInTheDocument();
      // s2 no part owns: a trailing group; s3 is hard: never offered
      expect(screen.getByText('Large gaps raise risk')).toBeInTheDocument();
      expect(screen.queryByText('Never offered: hard')).not.toBeInTheDocument();
    });

    it('Add hands the criterion to the Builder once and shows it as added; nothing is applied before', async () => {
      const { props } = setup();
      expect(props.onAcceptSuggestion).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole('button', { name: 'Add f.spread' }));
      expect(props.onAcceptSuggestion).toHaveBeenCalledTimes(1);
      expect(props.onAcceptSuggestion).toHaveBeenCalledWith(SPREAD);
      expect(screen.getByText('Added')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Add f.spread' })).not.toBeInTheDocument();
    });

    it('Skip leaves the screen alone and shows it as skipped', async () => {
      const { props } = setup();
      await userEvent.click(screen.getByRole('button', { name: 'Skip f.gap' }));
      expect(props.onAcceptSuggestion).not.toHaveBeenCalled();
      expect(screen.getByText('Skipped')).toBeInTheDocument();
    });
  });

  it('keeps the answer notes and the screen not-covered notes, each removable', async () => {
    const { props } = setup({ notes: ['A moat score that rises over time'] });
    expect(screen.getByText('assumed US listings')).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: 'Remove note: A moat score that rises over time' }),
    );
    expect(props.onRemoveNote).toHaveBeenCalledWith('A moat score that rises over time');
  });

  it('renders the grouped panel when parts are absent, null or empty', () => {
    for (const parts of [undefined, null, []]) {
      const { unmount } = setup({ answer: { ...ANSWER, parts } as ScreenDraft });
      expect(screen.getByRole('heading', { name: 'Applied' })).toBeInTheDocument();
      expect(screen.queryByRole('list', { name: 'Parts of your sentence' })).toBeNull();
      unmount();
    }
  });
});
