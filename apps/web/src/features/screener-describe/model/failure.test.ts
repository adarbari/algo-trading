import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/api';

import { draftFailure, wasCancelled } from './failure';

describe('draftFailure', () => {
  it('says drafting is off when the site has the text model off, without a retry', () => {
    const off = draftFailure(
      new ApiError(503, 'the text model is off: enable it in config/site/llm.toml (ADR 0041)'),
    );
    expect(off).toMatchObject({
      kind: 'off',
      help: { kind: 'term', id: 'describe_failure_off' },
      retry: false,
    });
    expect(
      draftFailure(new ApiError(503, 'the text model is forced off by ALGOTRADE_LLM=off')).kind,
    ).toBe('off');
  });

  it('never carries the raw server text, whatever the model said', () => {
    const failure = draftFailure(new ApiError(503, "the model's answer is not JSON"));
    expect(failure).toMatchObject({ kind: 'unavailable', retry: true });
    expect(JSON.stringify(failure)).not.toMatch(/JSON/);
  });

  it('maps a rate limit, a refusal and anything else', () => {
    expect(draftFailure(new ApiError(429, 'too many requests')).kind).toBe('busy');
    expect(draftFailure(new ApiError(400, 'sentence is empty')).kind).toBe('refused');
    expect(draftFailure(new ApiError(500, 'boom')).kind).toBe('unavailable');
    expect(draftFailure(new TypeError('Failed to fetch')).kind).toBe('unavailable');
  });
});

describe('wasCancelled', () => {
  it('is true only for an abort', () => {
    expect(wasCancelled(new DOMException('aborted', 'AbortError'))).toBe(true);
    expect(wasCancelled(new Error('x'))).toBe(false);
  });
});
