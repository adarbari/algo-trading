import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError, TestQueryProvider, type components } from '@/shared/api';

import type { ScreenDraft } from './hooks';
import { useRedraftPart } from './redraft';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  api: { POST: vi.fn() },
}));

const POST = vi.mocked(api.POST);
const wrapper = ({ children }: { children: ReactNode }) => (
  <TestQueryProvider>{children}</TestQueryProvider>
);

const PART: components['schemas']['Part'] = {
  id: 'p1',
  words: 'liquid',
  start: 0,
  end: 6,
  rank: false,
  join_words: '',
  reading: null,
  reading_source: 'model',
  kind: 'applied',
  origin: 'words',
  criteria: ['dv'],
  dropped: [],
  formulas: [],
  unresolved: [],
  missing: [],
  suggestions: [],
};
const ANSWER: ScreenDraft = {
  screener_id: 'mine',
  document: { id: 'mine', criteria: { dv: { field: 'f.dv', op: 'gte' } } },
  dropped: [{ id: 'iv', field: 'f.iv', reason: 'not in the catalogue' }],
  notes: ['assumed US'],
  sentence: 'liquid stocks',
  parts: [PART],
  draft_session_id: 'sess-1',
};
const DOCUMENT = { id: 'mine', criteria: { dv: { field: 'f.dv', op: 'gte', value: 9 } } };
const ok = (data: unknown) =>
  Promise.resolve({ data, response: new Response(null, { status: 200 }) }) as never;

beforeEach(() => {
  POST.mockReset();
});

describe('useRedraftPart', () => {
  it('posts the draft it holds with the Builder document, the part and its words, and returns the merged draft', async () => {
    const done = { draft: ANSWER, replaced_part_id: 'p1' };
    POST.mockReturnValue(ok(done));
    const { result } = renderHook(() => useRedraftPart('mine'), { wrapper });
    const signal = new AbortController().signal;
    result.current.mutate({
      answer: ANSWER,
      document: DOCUMENT,
      partId: 'p1',
      newWords: 'very liquid',
      signal,
    });
    await waitFor(() => {
      expect(result.current.data).toEqual(done);
    });
    expect(POST).toHaveBeenCalledWith('/screeners/{screener_id}/draft-part', {
      params: { path: { screener_id: 'mine' } },
      signal,
      body: {
        sentence: 'liquid stocks',
        parts: [PART],
        document: DOCUMENT,
        part_id: 'p1',
        new_words: 'very liquid',
        dropped: ANSWER.dropped,
        formulas: [],
        formulas_dropped: [],
        missing: [],
        notes: ['assumed US'],
        suggestions: [],
        suggestions_dropped: [],
        unresolved: [],
        draft_session_id: 'sess-1',
      },
    });
  });

  it('leaves the session out when the draft has none', async () => {
    POST.mockReturnValue(ok({ draft: ANSWER, replaced_part_id: 'p1' }));
    const { result } = renderHook(() => useRedraftPart('mine'), { wrapper });
    const { draft_session_id: _gone, ...bare } = ANSWER;
    result.current.mutate({ answer: bare, document: DOCUMENT, partId: 'p1', newWords: 'x' });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [, init] = POST.mock.calls[0] as unknown as [string, { body: object }];
    expect(init.body).not.toHaveProperty('draft_session_id');
  });

  it('fails with an ApiError that carries the limit code of a 429', async () => {
    POST.mockReturnValue(
      Promise.resolve({
        error: { detail: 'limit', code: 'part_redraft_limit', limit: 30, retry_after_s: 60 },
        response: new Response(null, { status: 429 }),
      }),
    );
    const { result } = renderHook(() => useRedraftPart('mine'), { wrapper });
    result.current.mutate({ answer: ANSWER, document: DOCUMENT, partId: 'p1', newWords: 'x' });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error).toMatchObject({ status: 429, code: 'part_redraft_limit' });
  });
});
