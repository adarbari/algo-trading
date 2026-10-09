import { afterEach, describe, expect, it, vi } from 'vitest';

import { accessToken, handleUnauthorized } from './auth';
import { ApiError } from './client';
import { TypedDocumentString } from './generated/graphql/graphql';
import { busyDelayMs, gql, GraphQLRequestError } from './graphql';

const document = new TypedDocumentString<{ session: { date: string } | null }, { day: string }>(
  'query Day($day: Date) { session(date: $day) { date } }',
);

const answer = (body: unknown, status = 200) =>
  vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));

vi.mock('./auth', () => ({
  accessToken: vi.fn(() => Promise.resolve<string | null>(null)),
  handleUnauthorized: vi.fn(() => Promise.resolve()),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(accessToken).mockResolvedValue(null);
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

  it('sends the access token as a bearer, and none when signed out', async () => {
    const fetch = answer({ data: { session: null } });
    vi.stubGlobal('fetch', fetch);
    await gql(document, { day: 'x' });
    const bare = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(bare.headers).not.toHaveProperty('authorization');
    vi.mocked(accessToken).mockResolvedValue('tok-1');
    await gql(document, { day: 'x' });
    const signed = (fetch.mock.calls[1] as unknown as [string, RequestInit])[1];
    expect(signed.headers).toMatchObject({ authorization: 'Bearer tok-1' });
  });

  it('ends the session on a 401 and rejects with an ApiError', async () => {
    vi.stubGlobal('fetch', answer({}, 401));
    await expect(gql(document, { day: 'x' })).rejects.toMatchObject({ status: 401 });
    expect(handleUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('waits the Retry-After of a 503 and asks again, quietly', async () => {
    vi.useFakeTimers();
    const busy = new Response('{}', { status: 503, headers: { 'retry-after': '2' } });
    const ok = new Response(JSON.stringify({ data: { session: null } }), { status: 200 });
    const fetch = vi.fn().mockResolvedValueOnce(busy).mockResolvedValueOnce(ok);
    vi.stubGlobal('fetch', fetch);
    const result = gql(document, { day: 'x' });
    await vi.advanceTimersByTimeAsync(3000); // at most 2 s * 1.5
    await expect(result).resolves.toEqual({ session: null });
    expect(fetch).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it('rejects with the 503 once the retries are used up', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn(() => Promise.resolve(new Response('{}', { status: 503 })));
    vi.stubGlobal('fetch', fetch);
    const settled = expect(gql(document, { day: 'x' })).rejects.toMatchObject({ status: 503 });
    await vi.advanceTimersByTimeAsync(60_000);
    await settled;
    expect(fetch).toHaveBeenCalledTimes(6);
    vi.useRealTimers();
  });

  it('spreads the wait by jitter around the growing Retry-After', () => {
    expect(busyDelayMs('2', 0)).toBeGreaterThanOrEqual(1000);
    expect(busyDelayMs('2', 0)).toBeLessThanOrEqual(3000);
    expect(busyDelayMs(null, 4)).toBeGreaterThan(1400);
    expect(new Set([1, 2, 3, 4, 5].map(() => busyDelayMs('2', 0))).size).toBeGreaterThan(1);
  });

  it('keeps the session on a 403 (a user the registry does not know)', async () => {
    vi.stubGlobal('fetch', answer({}, 403));
    await expect(gql(document, { day: 'x' })).rejects.toMatchObject({ status: 403 });
    expect(handleUnauthorized).not.toHaveBeenCalled();
  });
});
