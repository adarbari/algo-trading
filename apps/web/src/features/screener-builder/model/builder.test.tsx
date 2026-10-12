import { Button, Text, ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, gql, TestQueryProvider } from '@/shared/api';

import { PREVIEW_DEBOUNCE_MS, ScreenerBuilderProvider, useScreenerBuilder } from './builder';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    api: { POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
    gql: vi.fn(),
  };
});

const GQL = vi.mocked(gql);
const POST = vi.mocked(api.POST);
const PUT = vi.mocked(api.PUT);
const DELETE = vi.mocked(api.DELETE);
const ok = (data: unknown, status = 200) => ({ data, response: new Response(null, { status }) });

const WORKING = {
  criteria: {
    iv30: { field: 'rollup.iv30@v1.iv30', op: 'gte', value: 0.5, mode: 'hard' },
    close: { field: 'rollup.price_stats@v2.close', op: 'gt', value: 5, mode: 'hard' },
  },
};
const detail = (patch: Record<string, unknown> = {}) => ({
  screenerId: 'my',
  user: 'u',
  draft: { id: 'my', extends: 'vrp@1' },
  draftError: null,
  versions: [1],
  latest: 1,
  preset: { presetId: 'vrp', pinned: 1, current: 1, rebaseAvailable: false },
  hash: 'h',
  layers: [],
  resolved: {},
  error: null,
  working: WORKING,
  ...patch,
});
const FORMULA = (name: string, criterion: Record<string, unknown> | null) =>
  ({ name, expr: 'a - b', criterion }) as never;
const GAP = FORMULA('draft_gap', {
  field: 'feature.draft_gap',
  op: 'gte',
  value: 0.1,
  mode: 'hard',
});
const BARE = FORMULA('draft_bare', null);
const OTHER = FORMULA('draft_other', null);
const PREVIEW = { rows: [], summary: {}, funnel: [], decisions: {}, coverage: {}, total: 0 };
const V1 = [{ version: 1, document: { id: 'my', version: 1 } }];

/** Answers the screen's GraphQL reads: its detail (`screen`) and its versions. */
function serve(screen: unknown, versions: unknown[] = V1) {
  GQL.mockImplementation((document: unknown) =>
    Promise.resolve(
      String(document).includes('query ScreenVersions')
        ? { screenVersions: versions }
        : { screenDetail: screen },
    ),
  );
}

function Probe() {
  const b = useScreenerBuilder();
  return (
    <>
      <Text>{`status ${b.status} preset ${b.preset?.id ?? 'none'} dirty ${String(b.dirty)} next v${String(b.nextVersion)}`}</Text>
      <Text>{`criteria ${b.criteria.map((c) => `${c.id}=${String(c.value)}`).join(',')}`}</Text>
      <Text>{`idle ${String(b.preview.idle)} error ${b.errorCriterion ?? 'none'}`}</Text>
      <Button
        onClick={() => {
          const first = b.criteria[0];
          if (first) b.setCriterion({ ...first, value: 0.6 });
        }}
      >
        edit
      </Button>
      <Button
        onClick={() => {
          b.setTieBreak(null, 'desc');
        }}
      >
        clear tie-break
      </Button>
      <Button
        onClick={() => {
          b.addCriterion();
        }}
      >
        add
      </Button>
      <Button
        onClick={() => {
          b.addSuggested({ field: 'f.spread', op: 'lte', value: 0.01, mode: 'soft' });
        }}
      >
        add suggested
      </Button>
      <Button
        onClick={() => {
          b.removeCriterion('close');
        }}
      >
        remove
      </Button>
      <Button
        onClick={() => {
          void b.save();
        }}
      >
        save
      </Button>
      <Button
        onClick={() => {
          void b.discard();
        }}
      >
        discard
      </Button>
      <Button
        onClick={() => {
          b.setDraftSessionId('sess-1');
        }}
      >
        describe
      </Button>
      <Text>{`session ${b.draftSessionId ?? 'none'}`}</Text>
      <Button
        onClick={() => {
          b.recordChoice({ event: 'choice_made', subject: 'liquid', picked: 0 });
          b.recordChoice({ event: 'choice_made', subject: 'liquid', picked: 2 });
          b.skipFormula('draft_x');
        }}
      >
        decide
      </Button>
      <Button
        onClick={() => {
          b.setDraftSessionId(null);
        }}
      >
        end session
      </Button>
      <Text>{`choices ${b.choices.map((c) => `${c.event}:${c.subject}:${String(c.picked ?? '')}${c.feature ? `>${c.feature}` : ''}`).join(',')}`}</Text>
      <Text>{`formulas ${JSON.stringify(b.formulaStates)}`}</Text>
      <Text>{`pending ${b.pendingFormulas.map((f) => f.name).join(',')} reviewing ${b.reviewing?.name ?? 'none'}`}</Text>
      <Button
        onClick={() => {
          b.setFormulas([GAP, BARE]);
        }}
      >
        propose
      </Button>
      <Button
        onClick={() => {
          b.replaceFormulas([BARE, OTHER], ['draft_gap']);
        }}
      >
        redraft gap part
      </Button>
      <Button
        onClick={() => {
          b.reviewFormula(GAP);
        }}
      >
        review gap
      </Button>
      <Button
        onClick={() => {
          b.closeReview();
        }}
      >
        close review
      </Button>
      <Button
        onClick={() => {
          b.acceptFormula(GAP, 'feature.draft_gap');
        }}
      >
        accept gap
      </Button>
      <Button
        onClick={() => {
          b.acceptFormula(GAP, 'feature.my_gap');
        }}
      >
        accept gap renamed
      </Button>
      <Button
        onClick={() => {
          b.acceptFormula(BARE, 'feature.draft_bare');
        }}
      >
        accept bare
      </Button>
      <Button
        onClick={() => {
          b.skipFormula('draft_gap');
        }}
      >
        skip gap
      </Button>
      <Text>{`notes ${b.notes.join('|')}`}</Text>
      <Button
        onClick={() => {
          b.addNotes(['no support lines', 'no support lines', '  ']);
          b.loadDocument({ id: 'my', criteria: { iv30: { field: 'f.iv', op: 'gte', value: 1 } } });
        }}
      >
        note and load
      </Button>
      <Button
        onClick={() => {
          b.removeNote('no support lines');
        }}
      >
        remove note
      </Button>
    </>
  );
}

function setup() {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <ScreenerBuilderProvider id="my">
          <Probe />
        </ScreenerBuilderProvider>
      </TestQueryProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  for (const mock of [GQL, POST, PUT, DELETE]) mock.mockReset();
  serve(detail());
  POST.mockResolvedValue(ok(PREVIEW));
  PUT.mockResolvedValue(ok({ screener_id: 'my', document: {} }) as never);
  DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) });
});

describe('ScreenerBuilderProvider', () => {
  it('shows the draft resolved through its preset, and previews it', async () => {
    setup();
    expect(await screen.findByText('criteria iv30=0.5,close=5')).toBeInTheDocument();
    expect(screen.getByText('status ready preset none dirty false next v2')).toBeInTheDocument();
    expect(screen.getByText(/idle false/)).toBeInTheDocument();
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
    expect(POST.mock.calls[0]?.[1]).toMatchObject({
      body: { spec: { id: 'my', extends: 'vrp@1' } },
    });
  });

  it('an edit makes it dirty and the preview follows after the debounce, once', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
    const edited = performance.now();
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    expect(screen.getByText(/dirty true/)).toBeInTheDocument();
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(2);
    });
    expect(performance.now() - edited).toBeGreaterThanOrEqual(PREVIEW_DEBOUNCE_MS - 20);
    expect(POST.mock.calls[1]?.[1]).toMatchObject({
      body: { spec: { criteria: { iv30: { value: 0.6 } } } },
    });
  });

  it('leaves a criterion still being filled in out of the preview', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
    await userEvent.click(screen.getByRole('button', { name: 'add' }));
    expect(screen.getByText(/criteria iv30=0.5,close=5,criterion=undefined/)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, PREVIEW_DEBOUNCE_MS + 50));
    expect(POST).toHaveBeenCalledTimes(1);
  });

  it('adds an accepted suggestion as a new soft row under a fresh id, an edit', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'add suggested' }));
    expect(screen.getByText(/criteria iv30=0.5,close=5,spread=0.01/)).toBeInTheDocument();
    expect(screen.getByText(/dirty true/)).toBeInTheDocument();
  });

  it('saves the edited draft, then is clean', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(1);
    });
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({
      params: { path: { screener_id: 'my' } },
      body: { document: { id: 'my', extends: 'vrp@1', criteria: { iv30: { value: 0.6 } } } },
    });
    await waitFor(() => {
      expect(screen.getByText(/dirty false/)).toBeInTheDocument();
    });
  });

  it('sends the Describe-it session with the save, and has none for another screener', async () => {
    const view = setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'describe' }));
    expect(screen.getByText('session sess-1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(1);
    });
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({ body: { draft_session_id: 'sess-1' } });
    view.rerender(
      <ToastProvider>
        <TestQueryProvider>
          <ScreenerBuilderProvider id="other">
            <Probe />
          </ScreenerBuilderProvider>
        </TestQueryProvider>
      </ToastProvider>,
    );
    expect(await screen.findByText('session none')).toBeInTheDocument();
  });

  it('keeps the notes a drafted document replaces, saves them, and lets one be removed', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    expect(screen.getByText('notes')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'note and load' }));
    expect(screen.getByText('notes no support lines')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(1);
    });
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({
      body: { document: { notes: ['no support lines'] } },
    });
    await userEvent.click(screen.getByRole('button', { name: 'remove note' }));
    expect(screen.getByText('notes')).toBeInTheDocument();
  });

  it('keeps the latest decision per option, sends them with the save, and clears them with the session', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'describe' }));
    await userEvent.click(screen.getByRole('button', { name: 'decide' }));
    expect(
      screen.getByText('choices choice_made:liquid:2,formula_skipped:draft_x:'),
    ).toBeInTheDocument();
    expect(screen.getByText('formulas {"draft_x":"skipped"}')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(1);
    });
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({
      body: {
        choices: [
          { event: 'choice_made', subject: 'liquid', picked: 2 },
          { event: 'formula_skipped', subject: 'draft_x' },
        ],
      },
    });
    await userEvent.click(screen.getByRole('button', { name: 'end session' }));
    expect(screen.getByText('choices')).toBeInTheDocument();
    expect(screen.getByText('formulas {}')).toBeInTheDocument();
  });

  it('sends the choices with the save that follows them once, not with every autosave', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'describe' }));
    await userEvent.click(screen.getByRole('button', { name: 'decide' }));
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText('choices')).toBeInTheDocument(); // sent: dropped
    });
    expect(screen.getByText('formulas {"draft_x":"skipped"}')).toBeInTheDocument(); // still decided
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalledTimes(2);
    });
    expect(JSON.stringify(PUT.mock.calls[1]?.[1])).not.toContain('choices');
  });

  describe('proposed formulas', () => {
    const open = async () => {
      setup();
      await screen.findByText('criteria iv30=0.5,close=5');
      await userEvent.click(screen.getByRole('button', { name: 'propose' }));
    };

    it('keeps every proposal pending, out of the criteria, until it is decided', async () => {
      await open();
      expect(screen.getByText('pending draft_gap,draft_bare reviewing none')).toBeInTheDocument();
      expect(screen.getByText('criteria iv30=0.5,close=5')).toBeInTheDocument();
      expect(screen.getByText('formulas {}')).toBeInTheDocument();
    });

    it('opens and closes the review of one without deciding it', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'review gap' }));
      expect(screen.getByText(/reviewing draft_gap/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: 'close review' }));
      expect(screen.getByText('pending draft_gap,draft_bare reviewing none')).toBeInTheDocument();
    });

    it('accepting adds its criterion as an active row on the saved field, once, and records it', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'review gap' }));
      await userEvent.click(screen.getByRole('button', { name: 'accept gap' }));
      expect(screen.getByText('criteria iv30=0.5,close=5,draft_gap=0.1')).toBeInTheDocument();
      expect(screen.getByText('pending draft_bare reviewing none')).toBeInTheDocument();
      expect(screen.getByText('formulas {"draft_gap":"accepted"}')).toBeInTheDocument();
      expect(screen.getByText('choices formula_accepted:draft_gap:>draft_gap')).toBeInTheDocument();
      expect(screen.getByText(/dirty true/)).toBeInTheDocument();
    });

    it('records the saved feature name when the trader renamed the proposal', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'accept gap renamed' }));
      expect(screen.getByText('choices formula_accepted:draft_gap:>my_gap')).toBeInTheDocument();
    });

    it('accepting one with no criterion only accepts it', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'accept bare' }));
      expect(screen.getByText('criteria iv30=0.5,close=5')).toBeInTheDocument();
      expect(screen.getByText('formulas {"draft_bare":"accepted"}')).toBeInTheDocument();
    });

    it('skipping removes it from the pending rows, adds no criterion and records it', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'skip gap' }));
      expect(screen.getByText('pending draft_bare reviewing none')).toBeInTheDocument();
      expect(screen.getByText('criteria iv30=0.5,close=5')).toBeInTheDocument();
      expect(screen.getByText('choices formula_skipped:draft_gap:')).toBeInTheDocument();
    });

    it('redrafting one part swaps its proposals and keeps what was decided on the others', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'accept bare' }));
      await userEvent.click(screen.getByRole('button', { name: 'review gap' }));
      await userEvent.click(screen.getByRole('button', { name: 'redraft gap part' }));
      expect(screen.getByText('pending draft_other reviewing none')).toBeInTheDocument();
      expect(screen.getByText('formulas {"draft_bare":"accepted"}')).toBeInTheDocument();
    });

    it('a new answer replaces the proposals and forgets the decisions', async () => {
      await open();
      await userEvent.click(screen.getByRole('button', { name: 'skip gap' }));
      await userEvent.click(screen.getByRole('button', { name: 'propose' }));
      expect(screen.getByText('pending draft_gap,draft_bare reviewing none')).toBeInTheDocument();
      expect(screen.getByText('formulas {}')).toBeInTheDocument();
    });
  });

  it('drops the Describe-it session when the draft is discarded', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'describe' }));
    expect(screen.getByText('session sess-1')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'discard' }));
    expect(await screen.findByText('session none')).toBeInTheDocument();
  });

  it('switches an inherited criterion off instead of deleting it', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'remove' }));
    expect(screen.getByText('criteria iv30=0.5')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'save' }));
    await waitFor(() => {
      expect(PUT).toHaveBeenCalled();
    });
    expect(PUT.mock.calls[0]?.[1]).toMatchObject({
      body: { document: { criteria: { close: { enabled: false } } } },
    });
  });

  it('discards the saved draft and falls back to the latest version', async () => {
    setup();
    await screen.findByText('criteria iv30=0.5,close=5');
    await userEvent.click(screen.getByRole('button', { name: 'discard' }));
    await waitFor(() => {
      expect(DELETE).toHaveBeenCalledTimes(1);
    });
  });

  it('starts from the latest version when there is no draft', async () => {
    serve(detail({ draft: null }), [
      {
        version: 1,
        document: { id: 'my', version: 1, extends: 'vrp@1', criteria: { iv30: { value: 0.4 } } },
      },
    ]);
    setup();
    expect(await screen.findByText('criteria iv30=0.4,close=5')).toBeInTheDocument();
    expect(screen.getByText(/dirty false next v2/)).toBeInTheDocument();
  });

  describe('a site preset not copied yet', () => {
    const PRESET = { presetId: 'my', pinned: null, current: 4, rebaseAvailable: false };
    beforeEach(() => {
      serve(detail({ draft: null, versions: [], latest: null, preset: PRESET }));
      POST.mockImplementation(((path: string) =>
        Promise.resolve(
          path === '/screeners/{screener_id}/copy'
            ? ok({ screener_id: 'my', document: { id: 'my', extends: 'my@4' } }, 201)
            : ok(PREVIEW),
        )) as never);
    });
    const calls = (path: string) =>
      (POST.mock.calls as unknown as [string, unknown][]).filter(([p]) => p === path);

    it('previews as it is, at once, without making a copy', async () => {
      setup();
      expect(await screen.findByText(/preset my dirty false/)).toBeInTheDocument();
      await waitFor(() => {
        expect(calls('/screeners/preview')).toHaveLength(1);
      });
      expect(calls('/screeners/preview')[0]?.[1]).toMatchObject({
        body: { spec: { id: 'my', extends: 'my@4' } },
      });
      expect(calls('/screeners/{screener_id}/copy')).toHaveLength(0);
    });

    it('the first edit makes the pinned copy once, and carries on in it', async () => {
      setup();
      await screen.findByText(/preset my/);
      await userEvent.click(screen.getByRole('button', { name: 'edit' }));
      await userEvent.click(screen.getByRole('button', { name: 'add' }));
      expect(screen.getByText(/dirty true/)).toBeInTheDocument();
      await waitFor(() => {
        expect(calls('/screeners/{screener_id}/copy')).toHaveLength(1);
      });
      expect(calls('/screeners/{screener_id}/copy')[0]?.[1]).toMatchObject({
        params: { path: { screener_id: 'my' } },
        body: { preset: 'my' },
      });
      await userEvent.click(screen.getByRole('button', { name: 'save' }));
      await waitFor(() => {
        expect(PUT).toHaveBeenCalledTimes(1);
      });
      expect(PUT.mock.calls[0]?.[1]).toMatchObject({
        body: { document: { id: 'my', extends: 'my@4', criteria: { iv30: { value: 0.6 } } } },
      });
    });

    it('drops the edit when the copy cannot be made', async () => {
      POST.mockImplementation(((path: string) =>
        Promise.resolve(
          path === '/screeners/{screener_id}/copy'
            ? { error: { detail: 'taken' }, response: new Response(null, { status: 409 }) }
            : ok(PREVIEW),
        )) as never);
      setup();
      await screen.findByText(/preset my/);
      await userEvent.click(screen.getByRole('button', { name: 'edit' }));
      await waitFor(() => {
        expect(screen.getByText(/dirty false/)).toBeInTheDocument();
      });
    });

    it('clears the tie-break the preset sets, as an empty one in the copy', async () => {
      serve(
        detail({
          draft: null,
          versions: [],
          latest: null,
          preset: PRESET,
          working: { ...WORKING, rank: { tie_break: 'feature.spread' } },
        }),
      );
      setup();
      await screen.findByText(/preset my/);
      await userEvent.click(screen.getByRole('button', { name: 'clear tie-break' }));
      await userEvent.click(screen.getByRole('button', { name: 'save' }));
      await waitFor(() => {
        expect(PUT).toHaveBeenCalledTimes(1);
      });
      expect(PUT.mock.calls[0]?.[1]).toMatchObject({
        body: { document: { extends: 'my@4', rank: { tie_break: '' } } },
      });
    });
  });

  it('names the criterion a preview error comes from', async () => {
    POST.mockResolvedValue({
      error: { detail: 'my.criteria.close.field: unknown field' },
      response: new Response(null, { status: 400 }),
    });
    setup();
    expect(await screen.findByText(/error close/)).toBeInTheDocument();
  });

  it('reports a screen that failed to load', async () => {
    GQL.mockRejectedValue(new Error('the API is down'));
    setup();
    expect(await screen.findByText(/status error/)).toBeInTheDocument();
  });

  it('reports a screen that does not exist (a null detail)', async () => {
    serve(null);
    setup();
    expect(await screen.findByText(/status error/)).toBeInTheDocument();
  });
});
