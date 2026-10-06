import { describe, expect, it } from 'vitest';

import { decisionLabel, decisionTone, OUTCOME_FILL } from './decisions';

describe('decisions', () => {
  it('says a decision in words with its tone', () => {
    expect(decisionLabel('EVENT_RISK')).toBe('Event risk');
    expect(decisionTone('QUALIFIED')).toBe('positive');
    expect(decisionTone('WATCH')).toBe('accent');
    expect(decisionTone('EVENT_RISK')).toBe('warning');
    expect(decisionLabel('PAUSED')).toBe('Paused');
    expect(decisionTone('PAUSED')).toBe('warning');
    expect(decisionTone('OTHER')).toBe('neutral');
  });

  it('tints near misses and misses only', () => {
    expect([OUTCOME_FILL['PASS'], OUTCOME_FILL['NEAR'], OUTCOME_FILL['FAIL']]).toEqual([
      undefined,
      'warning',
      'negative',
    ]);
  });
});
