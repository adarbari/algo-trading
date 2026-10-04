import { describe, expect, it } from 'vitest';

import { ApiError, errorDetail, unwrap } from './client';

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
