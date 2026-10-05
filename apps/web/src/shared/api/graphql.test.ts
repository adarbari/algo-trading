import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './client';
import { TypedDocumentString } from './generated/graphql/graphql';
import { gql, GraphQLRequestError } from './graphql';

const document = new TypedDocumentString<{ session: { date: string } | null }, { day: string }>(
  'query Day($day: Date) { session(date: $day) { date } }',
);

const answer = (body: unknown, status = 200) =>
  vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('gql', () => {
  it('posts the operation and its variables, and resolves to its data', async () => {
    const fetch = answer({ data: { session: { date: '2026-10-02' } } });
    vi.stubGlobal('fetch', fetch);
    await expect(gql(document, { day: '2026-10-02' })).resolves.toEqual({
      session: { date: '2026-10-02' },
    });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/graphql');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      query: 'query Day($day: Date) { session(date: $day) { date } }',
      variables: { day: '2026-10-02' },
    });
  });

  it('rejects with the error codes the API sends', async () => {
    vi.stubGlobal(
      'fetch',
      answer({
        data: null,
        errors: [
          { message: "unknown field 'rollup.x@v1.y'", extensions: { code: 'UNKNOWN_FEATURE' } },
        ],
      }),
    );
    const failed = gql(document, { day: '2026-10-02' });
    await expect(failed).rejects.toBeInstanceOf(GraphQLRequestError);
    await expect(failed).rejects.toMatchObject({
      codes: ['UNKNOWN_FEATURE'],
      message: "unknown field 'rollup.x@v1.y'",
    });
  });

  it('rejects an HTTP failure and an answer without data', async () => {
    vi.stubGlobal('fetch', answer({}, 502));
    await expect(gql(document, { day: 'x' })).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal('fetch', answer({ data: null }));
    await expect(gql(document, { day: 'x' })).rejects.toMatchObject({ codes: ['INTERNAL'] });
  });
});
