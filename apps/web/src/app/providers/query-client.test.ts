import { describe, expect, it } from 'vitest';

import { ApiError, GraphQLRequestError } from '@/shared/api';

import { shouldRetry } from './query-client';

describe('shouldRetry', () => {
  it('never retries a 4xx answer: it will not change, so the query settles at once', () => {
    expect(shouldRetry(0, new ApiError(404, 'nothing stored'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'bad'))).toBe(false);
  });

  it('never retries a GraphQL error about the request; retries an internal one once', () => {
    const bad = new GraphQLRequestError([{ message: 'x', extensions: { code: 'BAD_REQUEST' } }]);
    expect(shouldRetry(0, bad)).toBe(false);
    expect(shouldRetry(0, new GraphQLRequestError([{ message: 'boom' }]))).toBe(true);
  });

  it('retries a network failure or a 5xx once, then settles', () => {
    expect(shouldRetry(0, new TypeError('Failed to fetch'))).toBe(true);
    expect(shouldRetry(0, new ApiError(503, 'down'))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'down'))).toBe(false);
  });
});
