import { Button, Text, ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';

import { PREVIEW_DEBOUNCE_MS, ScreenerBuilderProvider, useScreenerBuilder } from './builder';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() } };
});

const GET = vi.mocked(api.GET);
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
  screener_id: 'my',
  user: 'u',
  draft: { id: 'my', extends: 'vrp@1' },
  draft_error: null,
  versions: [1],
  latest: 1,
  preset: { preset_id: 'vrp', pinned: 1, current: 1, rebase_available: false },
  hash: 'h',
  layers: [],
  resolved: {},
  error: null,
  working: WORKING,
  ...patch,
});
const PREVIEW = { rows: [], summary: {}, funnel: [], decisions: {}, coverage: {}, total: 0 };

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
  for (const mock of [GET, POST, PUT, DELETE]) mock.mockReset();
  GET.mockImplementation(((path: string) =>
    Promise.resolve(
      path.endsWith('/versions')
        ? ok([{ version: 1, document: { id: 'my', version: 1 } }])
        : ok(detail()),
    )) as never);
  POST.mockResolvedValue(ok(PREVIEW));
  PUT.mockResolvedValue(ok({ screener_id: 'my', document: {} }) as never);
  DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) } as never);
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
    GET.mockImplementation(((path: string) =>
      Promise.resolve(
        path.endsWith('/versions')
          ? ok([
              {
                version: 1,
                document: {
                  id: 'my',
                  version: 1,
                  extends: 'vrp@1',
                  criteria: { iv30: { value: 0.4 } },
                },
              },
            ])
          : ok(detail({ draft: null })),
      )) as never);
    setup();
    expect(await screen.findByText('criteria iv30=0.4,close=5')).toBeInTheDocument();
    expect(screen.getByText(/dirty false next v2/)).toBeInTheDocument();
  });

  describe('a site preset not copied yet', () => {
    const PRESET = { preset_id: 'my', pinned: null, current: 4, rebase_available: false };
    beforeEach(() => {
      GET.mockImplementation((() =>
        Promise.resolve(
          ok(detail({ draft: null, versions: [], latest: null, preset: PRESET })),
        )) as never);
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
      GET.mockImplementation((() =>
        Promise.resolve(
          ok(
            detail({
              draft: null,
              versions: [],
              latest: null,
              preset: PRESET,
              working: { ...WORKING, rank: { tie_break: 'feature.spread' } },
            }),
          ),
        )) as never);
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
    GET.mockResolvedValue({
      error: { detail: 'no screen' },
      response: new Response(null, { status: 404 }),
    });
    setup();
    expect(await screen.findByText(/status error/)).toBeInTheDocument();
  });
});
