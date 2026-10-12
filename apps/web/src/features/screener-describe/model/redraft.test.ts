import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/api';

import { LIMIT_CODE, STALE, partFailure } from './redraft';

describe('partFailure', () => {
  it('reads the coded 429 as the daily limit: no retry, its own Guide term', () => {
    const failure = partFailure(new ApiError(429, 'daily limit of 30', LIMIT_CODE));
    expect(failure).toMatchObject({
      kind: 'limit',
      retry: false,
      help: { kind: 'term', id: 'describe_part_limit' },
    });
    expect(failure.title).not.toMatch(/30/); // the server's text is never shown
  });

  it('reads any other failure as a draft failure does, retry included', () => {
    expect(partFailure(new ApiError(429, 'slow down'))).toMatchObject({
      kind: 'busy',
      retry: true,
    });
    expect(partFailure(new ApiError(503, 'the text model is off'))).toMatchObject({
      kind: 'off',
      retry: false,
    });
    expect(partFailure(new ApiError(400, 'the new words are empty'))).toMatchObject({
      kind: 'refused',
      retry: true,
    });
    expect(partFailure(new TypeError('network'))).toMatchObject({ kind: 'unavailable' });
  });

  it('a stale answer can be tried again, with its own Guide term', () => {
    expect(STALE).toMatchObject({
      kind: 'stale',
      retry: true,
      help: { kind: 'term', id: 'describe_part_stale' },
    });
  });
});
