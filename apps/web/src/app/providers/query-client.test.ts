import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/api';

import { shouldRetry } from './query-client';

describe('shouldRetry', () => {
  it('never retries a 4xx answer: it will not change, so the query settles at once', () => {
    expect(shouldRetry(0, new ApiError(404, 'nothing stored'))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, 'bad'))).toBe(false);
  });

  it('retries a network failure or a 5xx once, then settles', () => {
    expect(shouldRetry(0, new TypeError('Failed to fetch'))).toBe(true);
    expect(shouldRetry(0, new ApiError(503, 'down'))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, 'down'))).toBe(false);
  });
});
