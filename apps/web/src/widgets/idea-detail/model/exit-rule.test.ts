import { describe, expect, it } from 'vitest';

import { exitRuleText } from './exit-rule';

const stop = {
  kind: 'HISTORY',
  fraction: 0.062,
  atr: null,
  multiple: null,
  winners: 80,
  beyond: 0.2,
} as const;

describe('exitRuleText', () => {
  it('names the served stop and hold and labels them backtested', () => {
    const text = exitRuleText({
      edgeId: 'a',
      stop,
      holdSessions: 5,
      winners: 80,
      inSampleOnly: false,
      unknown: null,
    });
    expect(text).toBe(
      'Historical exit rule: stop 6.2% below the entry close; hold 5 sessions. Backtested (hypothetical).',
    );
  });

  it('gives an ATR stop as its multiple, never a product', () => {
    const text = exitRuleText({
      edgeId: 'a',
      stop: { ...stop, kind: 'FALLBACK', fraction: null, atr: 1.4, multiple: 2 },
      holdSessions: null,
      winners: 3,
      inSampleOnly: false,
      unknown: null,
    });
    expect(text).toContain('stop 2.0 × ATR(14)');
    expect(text).not.toContain('hold');
  });

  it('is null when there is no stop and no hold to copy', () => {
    expect(
      exitRuleText({
        edgeId: 'a',
        stop: null,
        holdSessions: null,
        winners: 0,
        inSampleOnly: false,
        unknown: null,
      }),
    ).toBeNull();
  });
});
