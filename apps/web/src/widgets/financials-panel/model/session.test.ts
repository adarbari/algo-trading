import { describe, expect, it } from 'vitest';

import { sessionsDiffer } from './session';

describe('sessionsDiffer', () => {
  it('is false when every answer names the same session', () => {
    expect(sessionsDiffer(['2026-10-02', '2026-10-02', '2026-10-02'])).toBe(false);
  });

  it('is true when two answers name different sessions', () => {
    expect(sessionsDiffer(['2026-10-02', '2026-10-02', '2026-10-01'])).toBe(true);
  });

  it('ignores a request that has not answered or has no session', () => {
    expect(sessionsDiffer(['2026-10-02', undefined, null])).toBe(false);
    expect(sessionsDiffer([])).toBe(false);
  });
});
