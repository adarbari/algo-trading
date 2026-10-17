import { Button, Text } from '@algotrade/ui';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenDocument } from '@/entities/screen';
import type { DraftPart, ScreenDraft } from '@/features/screener-describe';
import { api, ApiError, TestQueryProvider, type components } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import DraftReview from './DraftReview';
import { RetypeCard } from './RetypePart';

vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`guide ${entry.id}`}</Text>,
}));
vi.mock('@/features/screener-describe', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useMyFeatureRequests: () => ({ data: [] }),
}));
vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  api: { POST: vi.fn() },
}));

const POST = vi.mocked(api.POST);
type Part = components['schemas']['Part'];

const FIFTY = { field: 'f.dollar_volume', op: 'gte', value: 50_000_000, mode: 'hard' };
const OPTIONABLE = { field: 'f.optionable', op: 'eq', value: true, mode: 'hard' };
const PRICE = { field: 'f.price', op: 'gte', value: 5, mode: 'hard' };
const DOCUMENT: ScreenDocument = {
  id: 'mine',
  criteria: { dollar_volume: { ...FIFTY }, optionable: { ...OPTIONABLE }, price: { ...PRICE } },
};

const PART: Omit<Part, 'id' | 'kind' | 'words'> = {
  start: 0,
  end: 0,
  rank: false,
  join_words: '',
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
  },
  {
    ...PART,
    id: 'p2',
    words: 'optionable stocks',
    kind: 'applied',
    reading: 'stocks with listed options',
    criteria: ['optionable'],
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
const ANSWER: ScreenDraft = {
  screener_id: 'mine',
  document: DOCUMENT,
  dropped: [],
  notes: [],
  unresolved: [
    {
      term: 'liquid',
      span: 'liquid',
      default_index: 0,
      alternatives: [
        { text: 'over $50M traded a day', criterion: FIFTY },
        { text: 'over $10M traded a day', criterion: { ...FIFTY, value: 10_000_000 } },
      ],
    },
  ],
  sentence: 'liquid optionable stocks',
  draft_session_id: 'sess-1',
  parts: PARTS,
};

/** What the server answers for a retyped "optionable stocks": the part's words and row changed. */
const NEXT: ScreenDraft = {
  ...ANSWER,
  sentence: 'liquid weekly options',
  document: {
    ...DOCUMENT,
    criteria: { ...DOCUMENT.criteria, weekly: { field: 'f.weekly', op: 'eq', value: true } },
  },
  parts: [
    PARTS[0] as Part,
    {
      ...(PARTS[1] as Part),
      words: 'weekly options',
      reading: 'has weekly expiries',
      criteria: ['weekly'],
    },
    PARTS[2] as Part,
  ],
};
const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) });
const failed = (status: number, body: unknown) =>
  Promise.resolve({ error: body, response: new Response(null, { status }) });

function Harness({
  onRedrafted,
  initial = DOCUMENT,
  withRedraft = true,
}: {
  onRedrafted?: (next: ScreenDraft, prior: ScreenDraft, part: DraftPart) => void;
  initial?: ScreenDocument;
  withRedraft?: boolean;
}) {
  const [answer, setAnswer] = useState(ANSWER);
  const [document, setDocument] = useState(initial);
  return (
    <TestQueryProvider>
      <Text>{`criteria ${Object.keys(document.criteria ?? {}).join(',')}`}</Text>
      <Button
        onClick={() => {
          setDocument({ ...document, criteria: { ...document.criteria, extra: PRICE } });
        }}
      >
        edit the screen
      </Button>
      <DraftReview
        answer={answer}
        document={document}
        formulaStates={{}}
        notes={[]}
        onRemoveNote={vi.fn()}
        onReviewFormula={vi.fn()}
        onSkipFormula={vi.fn()}
        onPickReading={(criterion) => {
          setDocument({
            ...document,
            criteria: { ...document.criteria, [criterion.id]: { ...criterion } },
          });
        }}
        onAcceptSuggestion={vi.fn()}
        {...(withRedraft
          ? {
              onRedrafted: (next: ScreenDraft, prior: ScreenDraft, part: DraftPart) => {
                onRedrafted?.(next, prior, part);
                setAnswer(next);
                setDocument(next.document as ScreenDocument);
              },
            }
          : {})}
      />
    </TestQueryProvider>
  );
}

const card = (name: string) => screen.getByRole('article', { name });
const retype = (name: string) =>
  within(card(name)).getByRole('button', { name: 'Retype this part' });
const open = async (name: string, words: string) => {
  await userEvent.click(retype(name));
  const input = within(card(name)).getByRole('textbox', { name: 'Retype this part' });
  await userEvent.clear(input);
  await userEvent.type(input, words);
  return input;
};
const redraft = (name: string) => within(card(name)).getByRole('button', { name: 'Redraft' });

beforeEach(() => {
  POST.mockReset();
});

describe('retyping one part', () => {
  it('offers Retype on a part with words only, and only when the owner can take the answer', () => {
    const view = render(<Harness />);
    expect(retype('liquid')).toBeEnabled();
    expect(retype('optionable stocks')).toBeEnabled();
    expect(
      within(card('Kept from your screen')).queryByRole('button', { name: 'Retype this part' }),
    ).toBeNull();
    view.unmount();
    render(<Harness withRedraft={false} />);
    expect(screen.queryByRole('button', { name: 'Retype this part' })).toBeNull();
  });

  it('turns the words into an input of at most 200 characters; Redraft waits for a change', async () => {
    render(<Harness />);
    await userEvent.click(retype('optionable stocks'));
    const input = within(card('optionable stocks')).getByRole('textbox', {
      name: 'Retype this part',
    });
    expect(input).toHaveValue('optionable stocks');
    expect(input).toHaveAttribute('maxlength', '200');
    expect(input).toHaveFocus();
    expect(redraft('optionable stocks')).toBeDisabled();
    await userEvent.type(input, ' x');
    expect(redraft('optionable stocks')).toBeEnabled();
    await userEvent.clear(input);
    expect(redraft('optionable stocks')).toBeDisabled();
  });

  it('Cancel and Escape leave with the words as they were and focus back on Retype', async () => {
    render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(
      within(card('optionable stocks')).getByRole('button', { name: 'Cancel' }),
    );
    expect(POST).not.toHaveBeenCalled();
    expect(within(card('optionable stocks')).queryByRole('textbox')).toBeNull();
    expect(retype('optionable stocks')).toHaveFocus();
    await userEvent.click(retype('optionable stocks'));
    expect(within(card('optionable stocks')).getByRole('textbox')).toHaveValue('optionable stocks');
    await userEvent.keyboard('{Escape}');
    expect(retype('optionable stocks')).toHaveFocus();
  });

  it('sends the draft it holds with the part and its new words, then swaps in the merged draft', async () => {
    POST.mockReturnValue(ok({ draft: NEXT, replaced_part_id: 'p2' }));
    const onRedrafted = vi.fn();
    const { container } = render(<Harness onRedrafted={onRedrafted} />);
    await open('optionable stocks', 'weekly   options');
    await userEvent.click(redraft('optionable stocks'));
    await waitFor(() => {
      expect(onRedrafted).toHaveBeenCalledTimes(1);
    });
    const [path, init] = POST.mock.calls[0] as unknown as [
      string,
      { body: Record<string, unknown> },
    ];
    expect(path).toBe('/screeners/{screener_id}/draft-part');
    expect(init.body).toMatchObject({
      sentence: 'liquid optionable stocks',
      part_id: 'p2',
      new_words: 'weekly options',
      document: DOCUMENT,
      draft_session_id: 'sess-1',
      parts: PARTS,
    });
    const [next, prior, part] = onRedrafted.mock.calls[0] as [ScreenDraft, ScreenDraft, DraftPart];
    expect([next, prior, part.id]).toEqual([NEXT, ANSWER, 'p2']);
    expect(await screen.findByRole('article', { name: 'weekly options' })).toBeInTheDocument();
    expect(screen.getByText('criteria dollar_volume,optionable,price,weekly')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the wait on that card only; the others stay usable but cannot start a retype', async () => {
    let answer: (value: unknown) => void = () => undefined;
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }) as never,
    );
    render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    const waiting = card('optionable stocks');
    expect(waiting).toHaveAttribute('data-state', 'redrafting');
    expect(within(waiting).getAllByText('Redrafting this part')).toHaveLength(2);
    expect(card('liquid')).toHaveAttribute('data-state', 'idle');
    expect(retype('liquid')).toBeDisabled();
    // another card's reading can still be picked while this one waits
    await userEvent.click(
      within(card('liquid')).getByRole('radio', { name: 'over $10M traded a day' }),
    );
    await act(async () => {
      answer({ data: NEXT, response: new Response(null, { status: 200 }) });
      await Promise.resolve();
    });
    // the screen changed meanwhile: the answer was built on the old rows
    expect(await screen.findByText('Your screen changed while this redrafted')).toBeInTheDocument();
    expect(
      within(card('optionable stocks')).getByText('guide describe_part_stale'),
    ).toBeInTheDocument();
    expect(card('optionable stocks')).toHaveAttribute('data-state', 'error');
    expect(retype('liquid')).toBeEnabled();
  });

  it('runs one retype at a time: a second input waits, and the first settling does not free a second turn early', async () => {
    let answer: (value: unknown) => void = () => undefined;
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }) as never,
    );
    render(<Harness />);
    await open('liquid', 'very liquid');
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    // the other card's input is open, but its Redraft is off while this one waits
    expect(redraft('liquid')).toBeDisabled();
    await userEvent.type(within(card('liquid')).getByRole('textbox'), '!');
    expect(redraft('liquid')).toBeDisabled();
    await userEvent.keyboard('{Enter}');
    expect(POST).toHaveBeenCalledTimes(1);
    await act(async () => {
      answer({
        data: { draft: NEXT, replaced_part_id: 'p2' },
        response: new Response(null, { status: 200 }),
      });
      await Promise.resolve();
    });
    await screen.findByRole('article', { name: 'weekly options' });
    expect(redraft('liquid')).toBeEnabled();
  });

  it('leaving mid-wait frees the one-at-a-time flag and abandons the call', async () => {
    POST.mockImplementation(() => new Promise(() => undefined) as never);
    const onRedrafting = vi.fn();
    const view = render(
      <TestQueryProvider>
        <RetypeCard
          card={{ kind: 'applied', kindLabel: 'Applied', words: 'liquid', redraftingLabel: 'Wait' }}
          part={PARTS[0] as Part}
          answer={ANSWER}
          document={DOCUMENT}
          edited={false}
          redrafting={null}
          onRedrafting={onRedrafting}
          limited={false}
          onLimited={vi.fn()}
          onRedrafted={vi.fn()}
        />
      </TestQueryProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Retype this part' }));
    await userEvent.type(screen.getByRole('textbox'), ' x{Enter}');
    expect(onRedrafting).toHaveBeenLastCalledWith('p1', true);
    const signal = (POST.mock.calls[0]?.[1] as { signal?: AbortSignal } | undefined)?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(onRedrafting).toHaveBeenLastCalledWith('p1', false);
  });

  it('asks before replacing the edits of a hand-edited part, and does not call the model on Cancel', async () => {
    POST.mockReturnValue(ok({ draft: NEXT, replaced_part_id: 'p2' }));
    const edited: ScreenDocument = {
      ...DOCUMENT,
      criteria: { ...DOCUMENT.criteria, optionable: { ...OPTIONABLE, mode: 'soft' } },
    };
    render(<Harness initial={edited} />);
    expect(within(card('optionable stocks')).getByText('Edited')).toBeInTheDocument();
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    const dialog = await screen.findByRole('dialog', { name: 'Replace this part?' });
    expect(within(dialog).getByText('This replaces your edits to this part.')).toBeInTheDocument();
    expect(POST).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(POST).not.toHaveBeenCalled();
    expect(within(card('optionable stocks')).getByRole('textbox')).toHaveValue('weekly options');
    await userEvent.click(redraft('optionable stocks'));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Redraft' }),
    );
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
  });

  it('does not ask for a part the trader has not edited', async () => {
    POST.mockReturnValue(ok({ draft: NEXT, replaced_part_id: 'p2' }));
    render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
  });

  it("still asks about another part's edits after a retype swapped the draft in", async () => {
    const edited: ScreenDocument = {
      ...DOCUMENT,
      criteria: { ...DOCUMENT.criteria, dollar_volume: { ...FIFTY, tolerance: 0.1 } },
    };
    // the merged draft carries the trader's edit to the other part, as the server returns it
    const merged: ScreenDraft = {
      ...NEXT,
      document: {
        ...NEXT.document,
        criteria: { ...edited.criteria, weekly: { field: 'f.weekly' } },
      },
    };
    POST.mockReturnValue(ok({ draft: merged, replaced_part_id: 'p2' }));
    render(<Harness initial={edited} />);
    expect(within(card('liquid')).getByText('Edited')).toBeInTheDocument();
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    await screen.findByRole('article', { name: 'weekly options' });
    expect(within(card('liquid')).getByText('Edited')).toBeInTheDocument();
    expect(within(card('weekly options')).queryByText('Edited')).toBeNull();
  });

  it('a failure is a message with Try again, which asks again from the same words', async () => {
    POST.mockReturnValueOnce(failed(503, { detail: 'provider exploded: key sk-123' }));
    POST.mockReturnValueOnce(ok({ draft: NEXT, replaced_part_id: 'p2' }));
    const { container } = render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    const part = card('optionable stocks');
    expect(await within(part).findByText('The model could not answer')).toBeInTheDocument();
    expect(screen.queryByText(/sk-123/)).toBeNull();
    expect(part).toHaveAttribute('data-state', 'error');
    expect(within(part).getByText('guide describe_failure_unavailable')).toBeInTheDocument();
    expect(within(part).getByRole('textbox')).toHaveValue('weekly options');
    await expectNoA11yViolations(container);
    await userEvent.click(within(part).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: 'weekly options' })).toBeInTheDocument();
    expect(POST).toHaveBeenCalledTimes(2);
  });

  it('the daily limit is its own state: no Try again, no further retype, the Guide says why', async () => {
    POST.mockReturnValue(
      failed(429, {
        detail: 'limit',
        code: 'part_redraft_limit',
        limit: 30,
        retry_after_s: 3600,
      }),
    );
    const { container } = render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    const part = card('optionable stocks');
    expect(
      await within(part).findByText('Daily limit of part redrafts reached'),
    ).toBeInTheDocument();
    expect(within(part).getByText('guide describe_part_limit')).toBeInTheDocument();
    expect(within(part).queryByRole('button', { name: 'Try again' })).toBeNull();
    expect(redraft('optionable stocks')).toBeDisabled();
    expect(retype('liquid')).toBeDisabled();
    expect(within(card('liquid')).getByText('help describe_part_limit')).toBeInTheDocument();
    await expectNoA11yViolations(container);
    await userEvent.click(within(part).getByRole('button', { name: 'Cancel' }));
    expect(retype('optionable stocks')).toBeDisabled();
    expect(POST).toHaveBeenCalledTimes(1);
  });

  it('the limit lifts for every card when the server retry-after elapses, with one timer', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      POST.mockReturnValue(
        failed(429, {
          detail: 'limit',
          code: 'part_redraft_limit',
          limit: 30,
          retry_after_s: 3600,
        }),
      );
      render(<Harness />);
      await open('optionable stocks', 'weekly options');
      await userEvent.click(redraft('optionable stocks'));
      const part = card('optionable stocks');
      expect(
        await within(part).findByText('Daily limit of part redrafts reached'),
      ).toBeInTheDocument();
      expect(redraft('optionable stocks')).toBeDisabled();
      expect(retype('liquid')).toBeDisabled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_599_000);
      });
      expect(retype('liquid')).toBeDisabled();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });
      expect(retype('liquid')).toBeEnabled();
      expect(within(part).queryByText('Daily limit of part redrafts reached')).toBeNull();
      expect(redraft('optionable stocks')).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a limit with no retry-after stays until the page reloads', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      POST.mockReturnValue(failed(429, { detail: 'limit', code: 'part_redraft_limit' }));
      render(<Harness />);
      await open('optionable stocks', 'weekly options');
      await userEvent.click(redraft('optionable stocks'));
      await screen.findByText('Daily limit of part redrafts reached');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(86_400_000);
      });
      expect(retype('liquid')).toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('another 429 is the busy message with Try again, not the limit', async () => {
    POST.mockReturnValue(failed(429, { detail: 'too many' }));
    render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    expect(await screen.findByText('Too many drafts')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(retype('liquid')).toBeEnabled();
  });

  it('a request the server refuses is shown as could not draft this', async () => {
    POST.mockImplementation(() => {
      throw new ApiError(400, 'the new words are empty');
    });
    render(<Harness />);
    await open('optionable stocks', 'weekly options');
    await userEvent.click(redraft('optionable stocks'));
    expect(await screen.findByText('Could not draft this')).toBeInTheDocument();
    expect(screen.queryByText(/the new words are empty/)).toBeNull();
  });
});
