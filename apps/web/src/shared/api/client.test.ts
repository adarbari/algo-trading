import { afterEach, describe, expect, it, vi } from 'vitest';

import { accessToken, handleUnauthorized } from './auth';
import { api, ApiError, errorDetail, unwrap } from './client';

// A Request needs an absolute URL; the app's default `/api` is relative to the page.
vi.mock('@/shared/config', () => ({ apiBaseUrl: 'http://api.test' }));
vi.mock('./auth', () => ({
  accessToken: vi.fn(() => Promise.resolve<string | null>(null)),
  handleUnauthorized: vi.fn(() => Promise.resolve()),
}));

afterEach(() => {
  vi.mocked(accessToken).mockResolvedValue(null);
});

const response = (status: number, statusText = ''): Response =>
  new Response(null, { status, statusText });

describe('unwrap', () => {
  it('returns the body of a successful response', async () => {
    await expect(
      unwrap(Promise.resolve({ data: { status: 'ok' }, response: response(200) })),
    ).resolves.toEqual({
      status: 'ok',
    });
  });

  it('throws an ApiError with the server detail', async () => {
    const failed = unwrap(
      Promise.resolve({ error: { detail: 'no such run' }, response: response(404) }),
    );
    await expect(failed).rejects.toBeInstanceOf(ApiError);
    await expect(failed).rejects.toMatchObject({ status: 404, message: 'API 404: no such run' });
  });
});

describe('errorDetail', () => {
  it('gives the server detail alone, else the error text', () => {
    expect(errorDetail(new ApiError(409, 'already exists'))).toBe('already exists');
    expect(errorDetail(new Error('offline'))).toBe('offline');
    expect(errorDetail('odd')).toBe('odd');
  });
});

describe('the REST client and the session', () => {
  const answer = (status: number) =>
    vi.fn((_request: Request) => Promise.resolve(new Response(JSON.stringify({}), { status })));

  it('sends the access token as a bearer, and none when signed out', async () => {
    const fetch = answer(200);
    await api.GET('/health', { fetch });
    expect(fetch.mock.calls[0]?.[0].headers.get('authorization')).toBeNull();
    vi.mocked(accessToken).mockResolvedValue('tok-1');
    await api.GET('/health', { fetch });
    expect(fetch.mock.calls[1]?.[0].headers.get('authorization')).toBe('Bearer tok-1');
  });

  it('ends the session on a 401 only', async () => {
    await api.GET('/health', { fetch: answer(403) });
    expect(handleUnauthorized).not.toHaveBeenCalled();
    await api.GET('/health', { fetch: answer(401) });
    expect(handleUnauthorized).toHaveBeenCalledTimes(1);
  });
});
